"""Bounded report-only evaluation for the repaired Apex-derived cohort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Sequence

import duckdb
import pandas as pd

from hypervector.research.apex_cohort_signals import (
    build_apex_mean_reversion_v2,
)
from hypervector.research.apex_cohort_evaluation_io import (
    archive_events as _archive_events,
    event_sha256 as _event_sha256,
    funding_frame as _funding_frame,
    funding_points as _funding_points,
    indexed as _indexed,
    load_funding as _load_funding,
    market_maker_sessions as _market_maker_sessions,
)
from hypervector.research.apex_regime_mm_policy import ApexMMPolicyConfig
from hypervector.research.apex_regime_mm_replay import (
    ApexMMReplayConfig,
    replay_apex_regime_mm_v2,
)
from hypervector.research.apex_regime_mm_replay_types import (
    ApexMMReplayResult,
    ReplayEvent,
)
from hypervector.research.low_tf_duckdb import (
    LowTimeframeInputFrames,
    load_low_timeframe_inputs,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)


_DIRECTIONAL_CANDIDATE = "apex_mean_reversion_v2"
_OI_CANDIDATE = "apex_oi_trend_v2"
_MM_CANDIDATE = "apex_regime_mm_v2"


@dataclass(frozen=True)
class ApexScreenRequest:
    """One validated candidate, segment, symbol, and evidence source."""

    candidate: str
    segment: str
    symbol: str
    start_utc: datetime
    end_utc: datetime
    database_path: Path
    funding_path: Path


def run_apex_candidate(request: ApexScreenRequest) -> dict[str, object]:
    """Run one bounded candidate evaluation without execution authority."""
    if request.symbol != "BTC":
        raise ValueError("the initial repaired Apex cohort is frozen to BTC")
    if request.candidate == _DIRECTIONAL_CANDIDATE:
        return _run_mean_reversion(request)
    if request.candidate == _OI_CANDIDATE:
        return _run_oi_coverage(request)
    if request.candidate == _MM_CANDIDATE:
        return _run_market_maker(request)
    raise ValueError(f"unknown Apex cohort candidate: {request.candidate}")


def _run_mean_reversion(request: ApexScreenRequest) -> dict[str, object]:
    inputs = load_low_timeframe_inputs(
        request.database_path,
        request.symbol,
        request.start_utc,
        request.end_utc,
        history_bars=0,
        horizon_bars=1,
    )
    bars = _indexed(inputs.bars, "bar_open_at")
    books = _indexed(inputs.books, "bar_open_at")
    raw_signals = build_apex_mean_reversion_v2(bars, books)
    window = bars.index.to_series().between(
        request.start_utc,
        request.end_utc,
        inclusive="left",
    )
    bars = bars.loc[window].copy()
    raw_signals = raw_signals.loc[bars.index]
    bars["funding_rate"] = _load_funding(
        request.funding_path,
        request.start_utc,
        request.end_utc,
        bars.index,
    )
    robust = request.segment == "robustness"
    signals = _directional_signals(raw_signals, request.candidate, robust)
    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        _directional_config(request, robust),
    )
    return _mean_reversion_result(request, inputs, bars, books, signals, report)


def _mean_reversion_result(
    request: ApexScreenRequest,
    inputs: LowTimeframeInputFrames,
    bars: pd.DataFrame,
    books: pd.DataFrame,
    signals: pd.DataFrame,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    metrics = report.to_dict()
    net = float(metrics["net_pnl_usd"])
    robust = request.segment == "robustness"
    return {
        "status": _result_status(net),
        "metrics": metrics,
        "input_counts": {
            "bars": len(bars),
            "book_bars": len(books.loc[books.index.intersection(bars.index)]),
            "missing_book_bars": inputs.missing_book_bars,
            "long_entries": int(signals["long_entry"].sum()),
            "short_entries": int(signals["short_entry"].sum()),
        },
        "input_fingerprints": {
            "bars_sha256": _frame_sha256(bars),
            "signals_sha256": _frame_sha256(signals),
        },
        "robustness_perturbation": (
            "one_additional_completed_bar_delay_and_5bps_slippage" if robust else "none"
        ),
        "limitations": [
            "the first 20 segment bars are causal feature warmup because pre-window bars are unavailable",
            "five-minute OHLC cannot resolve intrabar path ordering",
            "next-open fills use configured adverse slippage, not reconstructed L2 queue",
            "open-interest is not used by this candidate",
        ],
    }


def _directional_config(
    request: ApexScreenRequest,
    robustness: bool,
) -> SharedPortfolioConfig:
    slippage = 5.0 if robustness else 2.0
    return SharedPortfolioConfig(
        symbol=request.symbol,
        initial_equity=15_000.0,
        margin_fraction=0.10,
        leverage=5.0,
        venue_max_leverage=40.0,
        entry_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        max_hold_bars=36,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
    )


def _directional_signals(
    source: pd.DataFrame,
    candidate: str,
    robustness: bool,
) -> pd.DataFrame:
    """Translate explicit candidate exits into the shared simulator contract."""
    required = {
        "long_entry",
        "short_entry",
        "long_exit_mean",
        "long_exit_invalidation",
        "short_exit_mean",
        "short_exit_invalidation",
    }
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"directional Apex signals missing columns: {missing}")
    output = pd.DataFrame(index=source.index)
    output["long_entry"] = source["long_entry"].astype(bool)
    output["short_entry"] = source["short_entry"].astype(bool)
    output["long_exit"] = source[["long_exit_mean", "long_exit_invalidation"]].any(
        axis=1
    )
    output["short_exit"] = source[["short_exit_mean", "short_exit_invalidation"]].any(
        axis=1
    )
    output["signal_name"] = candidate
    if robustness:
        boolean_columns = ["long_entry", "short_entry", "long_exit", "short_exit"]
        output[boolean_columns] = output[boolean_columns].shift(1, fill_value=False)
    return output


def _run_oi_coverage(request: ApexScreenRequest) -> dict[str, object]:
    with duckdb.connect(str(request.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone='UTC'")
        expected = int(
            connection.execute(
                """
            SELECT count(*) FROM canonical_trade_5m_bars
            WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
            """,
                [request.symbol, request.start_utc, request.end_utc],
            ).fetchone()[0]
        )
        covered = int(
            connection.execute(
                """
            SELECT count(DISTINCT time_bucket(
                INTERVAL '5 minutes', to_timestamp(observed_ts_ms / 1000.0)
            ))
            FROM live_asset_contexts
            WHERE symbol = ?
              AND observed_ts_ms >= epoch_ms(?)
              AND observed_ts_ms < epoch_ms(?)
            """,
                [request.symbol, request.start_utc, request.end_utc],
            ).fetchone()[0]
        )
    coverage = _oi_coverage_status(covered, expected)
    return {
        **coverage,
        "metrics": {
            "completed_trades": 0,
            "net_pnl_usd": 0.0,
            "profit_factor": None,
            "maximum_drawdown_pct": 0.0,
            "liquidations": 0,
        },
        "limitations": [
            "no historical point-in-time open-interest archive covers the frozen window",
            "24-hour rolling volume is not substituted for true interval volume",
            "observer-only status grants no execution authority",
        ],
    }


def _oi_coverage_status(
    covered_bars: int,
    expected_bars: int,
) -> dict[str, object]:
    """Classify whether point-in-time OI covers a usable frozen segment."""
    if expected_bars <= 0 or covered_bars < 0:
        raise ValueError("OI coverage counts must be positive and non-negative")
    fraction = min(covered_bars / expected_bars, 1.0)
    return {
        "status": (
            "completed" if fraction >= 0.90 else "observer_only_insufficient_history"
        ),
        "covered_bars": covered_bars,
        "expected_bars": expected_bars,
        "coverage_fraction": fraction,
        "minimum_required_fraction": 0.90,
    }


def _run_market_maker(request: ApexScreenRequest) -> dict[str, object]:
    funding = _funding_frame(
        request.funding_path,
        request.start_utc,
        request.end_utc,
    )
    sessions = []
    for start, end in _market_maker_sessions(request.start_utc, request.end_utc):
        events = _archive_events(
            request.database_path,
            request.symbol,
            start,
            end,
        )
        points = _funding_points(funding, start, end)
        result = replay_apex_regime_mm_v2(
            events,
            points,
            _market_maker_config(request.segment == "robustness"),
        )
        sessions.append(_market_maker_session(result, events, start, end))
    return _market_maker_result(request, sessions)


def _market_maker_result(
    request: ApexScreenRequest,
    sessions: list[dict[str, object]],
) -> dict[str, object]:
    net = sum(float(session["net_pnl_usd"]) for session in sessions)
    gains = sum(max(float(session["net_pnl_usd"]), 0.0) for session in sessions)
    losses = -sum(min(float(session["net_pnl_usd"]), 0.0) for session in sessions)
    maker_markouts = [
        float(markout)
        for session in sessions
        for markout in session["maker_markouts_bps"]
    ]
    return {
        "status": _result_status(net),
        "metrics": _market_maker_metrics(sessions, net, gains, losses, maker_markouts),
        "sessions": sessions,
        "robustness_perturbation": (
            "150ms_submit_cancel_latency" if request.segment == "robustness" else "none"
        ),
        "limitations": [
            "fixed intrahour samples do not represent every minute in each segment",
            "public L2 cannot reveal private queue priority or hidden cancellations",
            "midpoint substitutes for unavailable historical mark price",
            "profit factor is computed from independent session net outcomes",
        ],
    }


def _market_maker_metrics(
    sessions: list[dict[str, object]],
    net: float,
    gains: float,
    losses: float,
    maker_markouts: list[float],
) -> dict[str, object]:
    return {
        "session_count": len(sessions),
        "sampled_hours": len(sessions) * 0.5,
        "net_pnl_usd_fixed_session_notional": net,
        "profit_factor_by_session": gains / losses if losses else None,
        "maximum_drawdown_pct": min(
            float(session["maximum_drawdown_pct"]) for session in sessions
        ),
        "maker_fills": sum(int(session["maker_fill_count"]) for session in sessions),
        "taker_fills": sum(int(session["taker_fill_count"]) for session in sessions),
        "fees_usd": sum(float(session["fees_usd"]) for session in sessions),
        "funding_cashflow_usd": sum(
            float(session["funding_cashflow_usd"]) for session in sessions
        ),
        "liquidations": sum(int(session["liquidations"]) for session in sessions),
        "minimum_liquidation_distance_pct": _minimum_optional(
            session["minimum_liquidation_distance_pct"] for session in sessions
        ),
        "mean_maker_markout_bps": (
            sum(maker_markouts) / len(maker_markouts) if maker_markouts else None
        ),
        "queue_depleted_quantity": sum(
            float(session["queue_depleted_quantity"]) for session in sessions
        ),
    }


def _market_maker_config(robustness: bool) -> ApexMMReplayConfig:
    latency = 150 if robustness else 50
    return ApexMMReplayConfig(
        policy=ApexMMPolicyConfig(
            tick_size=1.0,
            base_order_notional_usd=150.0,
            maximum_inventory_fraction=0.10,
        ),
        initial_equity_usd=15_000.0,
        submit_latency_ms=latency,
        cancel_latency_ms=latency,
        quote_refresh_ms=1_000,
        leverage=3.0,
    )


def _market_maker_session(
    result: ApexMMReplayResult,
    events: Sequence[ReplayEvent],
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    fills = result.fills
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "event_count": len(events),
        "event_sha256": _event_sha256(events),
        "net_pnl_usd": result.net_pnl_usd,
        "maximum_drawdown_pct": result.maximum_drawdown_pct,
        "maker_fill_count": result.maker_fill_count,
        "taker_fill_count": result.taker_fill_count,
        "fees_usd": result.maker_fees_usd + result.taker_fees_usd,
        "funding_cashflow_usd": result.funding_cashflow_usd,
        "liquidations": result.liquidations,
        "minimum_liquidation_distance_pct": result.minimum_liquidation_distance_pct,
        "queue_depleted_quantity": result.queue_depleted_quantity,
        "maker_markouts_bps": [
            fill.markout_bps
            for fill in fills
            if fill.liquidity_side == "maker" and fill.markout_bps is not None
        ],
    }


def _result_status(net_pnl_usd: float) -> str:
    if net_pnl_usd > 0.0:
        return "completed_positive"
    if net_pnl_usd < 0.0:
        return "completed_negative"
    return "completed_flat"


def _minimum_optional(values: Iterable[object]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return min(numbers) if numbers else None


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256("\x1f".join(map(str, frame.columns)).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return digest.hexdigest()
