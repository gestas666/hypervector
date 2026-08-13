"""Gap-causal backward validation for the frozen SOL range-onset rule."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_api import validate_window
from hypervector.data.oxa_candles import repair_candle_cadence
from hypervector.data.provenance import normalize_ohlcv
from hypervector.research.range_onset_signals import build_range_onset_signals
from hypervector.research.sol_range_onset_backward_evidence import (
    sha256,
    validate_backward_manifest,
    validate_backward_manifest_rows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
    SharedPortfolioTrade,
)

SignalBuilder = Callable[[pd.DataFrame], pd.DataFrame]
_INITIAL_EQUITY = 15_000.0
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class PreparedGapBlock:
    """One continuous candle block after only bounded continuity repair."""

    number: int
    start: pd.Timestamp
    end: pd.Timestamp
    raw_rows: int
    gap_fill_rows: int
    bars: pd.DataFrame


def prepare_gap_safe_blocks(
    frame: pd.DataFrame,
    *,
    max_gap_minutes: int = 30,
) -> tuple[PreparedGapBlock, ...]:
    """Split large outages and repair only smaller missing-minute runs."""
    if max_gap_minutes < 1:
        raise ValueError("max_gap_minutes must be positive")
    bars = normalize_ohlcv(frame)
    if bars.empty or bars["timestamp"].duplicated().any():
        raise ValueError("SOL backward candles must be non-empty and unique")
    threshold = pd.Timedelta(minutes=max_gap_minutes + 1)
    deltas = bars["timestamp"].diff()
    breaks = [
        position
        for position, delta in enumerate(deltas)
        if pd.notna(delta) and delta > threshold
    ]
    bounds = (0, *breaks, len(bars))
    return tuple(
        _prepare_block(number, bars.iloc[lo:hi], max_gap_minutes)
        for number, (lo, hi) in enumerate(zip(bounds, bounds[1:]), start=1)
    )


def evaluate_sol_backward_challenge(
    *,
    bars_path: Path,
    funding_path: Path,
    start: datetime,
    end: datetime,
    signal_builder: SignalBuilder = build_range_onset_signals,
    max_gap_minutes: int = 30,
    warmup_hours: int = 30,
) -> dict[str, object]:
    """Evaluate the frozen SOL recipe on previously unused backward history."""
    validate_window(start, end)
    if warmup_hours < 30:
        raise ValueError("SOL backward challenge requires at least 30 warmup hours")
    bars, funding = load_verified_sol_backward_inputs(
        bars_path=bars_path,
        funding_path=funding_path,
        start=start,
        end=end,
    )
    blocks = prepare_gap_safe_blocks(bars, max_gap_minutes=max_gap_minutes)
    rows, reports = _evaluate_blocks(blocks, funding, signal_builder, warmup_hours)
    return _artifact(
        bars_path,
        funding_path,
        start,
        end,
        bars,
        funding,
        rows,
        reports,
        max_gap_minutes,
        warmup_hours,
    )


def load_verified_sol_backward_inputs(
    *,
    bars_path: Path,
    funding_path: Path,
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load checksum-verified SOL candles and complete official funding."""
    bar_manifest = validate_backward_manifest(
        bars_path, "0xarchive_hyperliquid_candles", start, end, interval="1m"
    )
    funding_manifest = validate_backward_manifest(
        funding_path, "hl_funding_history", start, end
    )
    bars = _load_bars(bars_path, start, end)
    funding = _load_funding(funding_path, start, end)
    validate_backward_manifest_rows(bar_manifest, len(bars), "candle")
    validate_backward_manifest_rows(funding_manifest, len(funding), "funding")
    return bars, funding


def _prepare_block(
    number: int,
    raw: pd.DataFrame,
    max_gap_minutes: int,
) -> PreparedGapBlock:
    start = pd.Timestamp(raw["timestamp"].iloc[0])
    end = pd.Timestamp(raw["timestamp"].iloc[-1]) + _MINUTE
    repaired, fills = repair_candle_cadence(
        raw,
        start=start.to_pydatetime(),
        end=end.to_pydatetime(),
        max_gap_minutes=max_gap_minutes,
    )
    indexed = repaired.set_index("timestamp")
    return PreparedGapBlock(number, start, end, len(raw), fills, indexed)


def _load_bars(path: Path, start: datetime, end: datetime) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"SOL backward candles are missing: {path}")
    frame = pd.read_parquet(path)
    bars = normalize_ohlcv(frame)
    mask = (bars["timestamp"] >= start) & (bars["timestamp"] < end)
    bars = bars.loc[mask].reset_index(drop=True)
    if set(bars["source"].unique()) != {"hl"}:
        raise ValueError("SOL backward candles must be immutable Hyperliquid rows")
    return bars


def _load_funding(path: Path, start: datetime, end: datetime) -> pd.Series:
    if not path.is_file():
        raise FileNotFoundError(f"SOL backward funding is missing: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "funding_rate", "source"}
    if not required.issubset(frame.columns):
        raise ValueError("SOL backward funding has missing columns")
    if set(frame["source"].astype(str).unique()) != {"hl_funding_history"}:
        raise ValueError("SOL backward funding must be official Hyperliquid history")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.loc[
        (frame["timestamp"] >= start) & (frame["timestamp"] < end)
    ].set_index("timestamp")
    if frame.index.duplicated().any():
        raise ValueError("SOL backward funding contains duplicate hours")
    expected = pd.date_range(start, end, freq="1h", inclusive="left")
    rates = frame["funding_rate"].astype(float).reindex(expected)
    if rates.isna().any() or not rates.map(math.isfinite).all():
        raise ValueError("SOL backward funding is incomplete or non-finite")
    return rates


def _evaluate_blocks(
    blocks: tuple[PreparedGapBlock, ...],
    funding: pd.Series,
    signal_builder: SignalBuilder,
    warmup_hours: int,
) -> tuple[list[dict[str, object]], list[SharedPortfolioReport]]:
    rows: list[dict[str, object]] = []
    reports: list[SharedPortfolioReport] = []
    for block in blocks:
        row, report = _evaluate_block(block, funding, signal_builder, warmup_hours)
        rows.append(row)
        if row["status"] == "complete" and report is not None:
            reports.append(report)
    return rows, reports


def _evaluate_block(
    block: PreparedGapBlock,
    funding: pd.Series,
    signal_builder: SignalBuilder,
    warmup_hours: int,
) -> tuple[dict[str, object], SharedPortfolioReport | None]:
    bars = _attach_funding(block.bars, funding)
    execution_start = block.start + pd.Timedelta(hours=warmup_hours)
    execution = bars.loc[bars.index >= execution_start]
    base = _block_identity(block, execution_start, len(execution))
    if len(execution) < 2:
        return {**base, "status": "insufficient_warmup"}, None
    signals = signal_builder(bars).loc[execution.index]
    report = evaluate_shared_bar_portfolio(execution, signals, _risk_config())
    status = "censored_end_boundary" if report.forced_end_exits else "complete"
    return {
        **base,
        "status": status,
        "entry_signals": _entry_counts(signals),
        "metrics": report.to_dict(),
    }, report


def _attach_funding(bars: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    enriched = bars.copy()
    enriched["funding_rate"] = 0.0
    common = enriched.index.intersection(funding.index)
    enriched.loc[common, "funding_rate"] = funding.loc[common].to_numpy()
    return enriched


def _risk_config() -> SharedPortfolioConfig:
    return SharedPortfolioConfig(
        symbol="SOL",
        initial_equity=_INITIAL_EQUITY,
        margin_fraction=0.03,
        leverage=5.0,
        venue_max_leverage=20.0,
        stop_margin_pct=3.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=2.0,
        market_exit_slippage_bps=2.0,
        max_hold_bars=48 * 60,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=True,
    )


def _block_identity(
    block: PreparedGapBlock,
    execution_start: pd.Timestamp,
    execution_rows: int,
) -> dict[str, object]:
    return {
        "block": block.number,
        "start_utc": block.start.isoformat(),
        "end_utc": block.end.isoformat(),
        "execution_start_utc": execution_start.isoformat(),
        "raw_rows": block.raw_rows,
        "gap_fill_rows": block.gap_fill_rows,
        "execution_rows": execution_rows,
        "execution_authority": "none",
    }


def _entry_counts(signals: pd.DataFrame) -> dict[str, int]:
    return {
        "long": int(signals["long_entry"].astype(bool).sum()),
        "short": int(signals["short_entry"].astype(bool).sum()),
    }


def _artifact(
    bars_path: Path,
    funding_path: Path,
    start: datetime,
    end: datetime,
    bars: pd.DataFrame,
    funding: pd.Series,
    rows: list[dict[str, object]],
    reports: list[SharedPortfolioReport],
    max_gap_minutes: int,
    warmup_hours: int,
) -> dict[str, object]:
    statuses = [str(row["status"]) for row in rows]
    return {
        "schema_version": 1,
        "mode": "sol_range_onset_backward_temporal_validation_bar_only",
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "place_attempted": False,
        "submitted": False,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "block_count": len(rows),
        "complete_block_count": statuses.count("complete"),
        "censored_block_count": statuses.count("censored_end_boundary"),
        "insufficient_warmup_block_count": statuses.count("insufficient_warmup"),
        "frozen_recipe": _recipe(max_gap_minutes, warmup_hours),
        "data_evidence": _data_evidence(bars_path, funding_path, bars, funding),
        "blocks": rows,
        "aggregate": aggregate_reset_block_reports(reports),
        "limitations": _limitations(),
    }


def _recipe(max_gap_minutes: int, warmup_hours: int) -> dict[str, object]:
    return {
        "signal": "completed_1h_10x30_sma_cross",
        "entry_regime": ["5m_RANGE", "5m_BREAKOUT"],
        "stop_bps": 60.0,
        "target": None,
        "maximum_hold_hours": 48,
        "margin_fraction": 0.03,
        "leverage": 5.0,
        "effective_notional_fraction": 0.15,
        "entry_exit_slippage_bps": 2.0,
        "taker_fee_rate": 0.00045,
        "maximum_gap_repair_minutes": max_gap_minutes,
        "causal_warmup_hours": warmup_hours,
        "selected_before_backward_window_was_inspected": True,
    }


def _data_evidence(
    bars_path: Path,
    funding_path: Path,
    bars: pd.DataFrame,
    funding: pd.Series,
) -> dict[str, object]:
    gaps = _gap_evidence(bars)
    return {
        "bars_path": str(bars_path.resolve()),
        "bars_sha256": sha256(bars_path),
        "bars_manifest_sha256": sha256(bars_path.parent / "manifest.json"),
        "raw_bar_rows": len(bars),
        "funding_path": str(funding_path.resolve()),
        "funding_sha256": sha256(funding_path),
        "funding_manifest_sha256": sha256(funding_path.parent / "manifest.json"),
        "funding_events": len(funding),
        **gaps,
    }


def _gap_evidence(bars: pd.DataFrame) -> dict[str, int]:
    deltas = bars["timestamp"].diff().dropna()
    missing = (deltas[deltas > _MINUTE] / _MINUTE - 1).astype(int)
    return {
        "source_gap_count": len(missing),
        "source_missing_minutes": int(missing.sum()),
        "source_outages_above_30m": int(missing.gt(30).sum()),
        "maximum_source_gap_minutes": int(missing.max()) if len(missing) else 0,
    }


def aggregate_reset_block_reports(
    reports: list[SharedPortfolioReport],
) -> dict[str, object]:
    """Aggregate independent complete reports without bridging outages."""
    trades = tuple(trade for report in reports for trade in report.trades)
    gross_profit = sum(report.gross_profit_usd for report in reports)
    gross_loss = sum(report.gross_loss_usd for report in reports)
    product_equity = _INITIAL_EQUITY * math.prod(
        report.final_equity / _INITIAL_EQUITY for report in reports
    )
    return {
        "included_blocks": len(reports),
        "profitable_blocks": sum(report.net_pnl_usd > 0.0 for report in reports),
        "completed_trades": len(trades),
        "wins": sum(trade.net_pnl_usd > 0.0 for trade in trades),
        "losses": sum(trade.net_pnl_usd <= 0.0 for trade in trades),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
        "reset_block_net_pnl_usd": sum(report.net_pnl_usd for report in reports),
        "product_equity_usd": product_equity,
        "product_return_pct": 100.0 * (product_equity / _INITIAL_EQUITY - 1.0),
        "worst_block_drawdown_pct": min(
            (report.maximum_drawdown_pct for report in reports), default=0.0
        ),
        "liquidations": sum(report.liquidations for report in reports),
        "forced_end_exits": sum(report.forced_end_exits for report in reports),
        "same_bar_ambiguous_trades": sum(trade.same_bar_ambiguous for trade in trades),
        "total_fees_usd": sum(report.total_fees_usd for report in reports),
        "funding_cashflow_usd": sum(report.funding_cashflow_usd for report in reports),
        "long": _direction_metrics(trades, "long"),
        "short": _direction_metrics(trades, "short"),
        "leave_one_block_out": _leave_one_block_out(reports),
    }


def _direction_metrics(
    trades: tuple[SharedPortfolioTrade, ...],
    direction: str,
) -> dict[str, int | float | None]:
    selected = tuple(trade for trade in trades if trade.direction == direction)
    profits = tuple(trade.net_pnl_usd for trade in selected if trade.net_pnl_usd > 0)
    losses = tuple(-trade.net_pnl_usd for trade in selected if trade.net_pnl_usd <= 0)
    gross_profit, gross_loss = sum(profits), sum(losses)
    return {
        "completed_trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in selected),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
    }


def _leave_one_block_out(
    reports: list[SharedPortfolioReport],
) -> list[dict[str, int | float]]:
    rows: list[dict[str, int | float]] = []
    for omitted in range(len(reports)):
        equity = _INITIAL_EQUITY * math.prod(
            report.final_equity / _INITIAL_EQUITY
            for index, report in enumerate(reports)
            if index != omitted
        )
        rows.append(
            {"omitted_complete_block": omitted + 1, "product_equity_usd": equity}
        )
    return rows


def _limitations() -> list[str]:
    return [
        "this is bar-only backward validation, not executable L2 evidence",
        "the frozen rule was selected on the later 2025-07-28 to 2026-07-28 year",
        "bounded missing minutes are explicit zero-volume continuity fills",
        "large provider outages split independently reset blocks and are not bridged",
        "a block ending with an open position is censored rather than force-counted",
        "the backward window is consumed by this result and cannot be reused as untouched",
    ]
