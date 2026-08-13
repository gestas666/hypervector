"""Paired baseline contracts for the BTC 15-minute maker-entry screen."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd

from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.market_cipher_maker_entry import (
    MakerEntryConfig,
    MakerEntryOutcome,
    MakerEntryRequest,
    build_maker_replay_signal,
    reconstruct_maker_entry,
)
from hypervector.research.market_cipher_replay import evaluate_market_cipher_replay
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
)
from hypervector.research.market_cipher_maker_reporting import (
    build_maker_report,
    replay_trade_frame,
)
from hypervector.research.market_cipher_strategy_research import (
    resolve_market_cipher_replay_config,
)

ChronologicalSegment = Literal["development", "validation", "pseudo_holdout"]

_PROFILE = "hulk_expansion_bidirectional_tuned_v2"
_SIGNAL_COLUMNS = {
    "candidate",
    "signal_time_utc",
    "side",
    "score",
    "eligible",
    "stop_anchor",
    "symbol",
}
_TRADE_COLUMNS = {
    "candidate",
    "signal_score",
    "symbol",
    "direction",
    "signal_time_utc",
    "entry_time_utc",
    "entry_price",
    "initial_quantity",
}
_BASELINE_PARAMETERS = {
    "initial_equity": 15_000.0,
    "risk_fraction": 0.0025,
    "leverage": 5.0,
    "minimum_stop_bps": 20.0,
    "maximum_stop_bps": 75.0,
    "target_r_multiple": 3.0,
}


@dataclass(frozen=True)
class PairedMakerRequest:
    """One accepted market-entry trade paired to its originating signal."""

    signal_time_utc: pd.Timestamp
    candidate: str
    request: MakerEntryRequest


@dataclass(frozen=True)
class MarketCipherMakerResearchRun:
    """Immutable report plus entry and completed-trade sidecars."""

    report: dict[str, object]
    entries: pd.DataFrame
    trades: pd.DataFrame


def resolve_maker_replay_config() -> MarketCipherReplayConfig:
    """Return the preregistered one-minute lifecycle and maker friction."""
    baseline = resolve_market_cipher_replay_config("nominal", bar_minutes=15)
    return replace(
        baseline,
        maximum_hold_bars=1_440,
        entry_fee_rate=0.00015,
        entry_slippage_bps=0.0,
    )


def run_market_cipher_maker_research(
    *,
    database_path: Path,
    baseline_path: Path,
    funding_paths: tuple[Path, ...],
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    segment: ChronologicalSegment,
    entry_config: MakerEntryConfig = MakerEntryConfig(),
) -> MarketCipherMakerResearchRun:
    """Run the frozen paired maker-entry counterfactual without authority."""
    start, end = _window(start_utc, end_utc)
    baseline_report, signals, trades = _load_baseline(baseline_path)
    validate_maker_baseline(
        baseline_report,
        signals,
        trades,
        start_utc=start,
        end_utc=end,
        segment=segment,
    )
    pairs = build_paired_maker_requests(signals, trades)
    entries, maker_signals = _reconstruct_all(database_path, pairs, entry_config)
    bars = _load_one_minute_bars(database_path, start, end)
    funding = load_verified_hourly_funding(
        list(funding_paths),
        bars.index.min(),
        bars.index.max() + pd.Timedelta(minutes=1),
    )
    replay_bars = attach_hourly_funding(bars, funding)
    replay_bars["wave_cross"] = 0
    config = resolve_maker_replay_config()
    replay = evaluate_market_cipher_replay({"BTC": replay_bars}, maker_signals, config)
    report = build_maker_report(
        baseline_path=baseline_path,
        baseline_report=baseline_report,
        signal_count=len(signals),
        paired_trade_count=len(pairs),
        entries=entries,
        bars=replay_bars,
        replay=replay,
        replay_config=config,
        entry_config=entry_config,
        start=start,
        end=end,
        segment=segment,
    )
    return MarketCipherMakerResearchRun(report, entries, replay_trade_frame(replay))


def validate_maker_baseline(
    report: dict[str, object],
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    segment: ChronologicalSegment,
) -> None:
    """Reject a baseline that differs from the frozen paired experiment."""
    _validate_report_identity(report, start_utc, end_utc, segment)
    _require_columns(signals, _SIGNAL_COLUMNS, "baseline signals")
    _require_columns(trades, _TRADE_COLUMNS, "baseline trades")
    if signals.empty or trades.empty:
        raise ValueError("maker baseline requires non-empty signals and trades")
    if set(signals["symbol"].astype(str)) != {"BTC"}:
        raise ValueError("maker baseline signals must contain only BTC")
    if set(trades["symbol"].astype(str)) != {"BTC"}:
        raise ValueError("maker baseline trades must contain only BTC")
    build_paired_maker_requests(signals, trades)


def build_paired_maker_requests(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
) -> tuple[PairedMakerRequest, ...]:
    """Pair each accepted baseline trade with exactly one causal signal."""
    _require_columns(signals, _SIGNAL_COLUMNS, "baseline signals")
    _require_columns(trades, _TRADE_COLUMNS, "baseline trades")
    normalized = signals.copy()
    normalized["signal_time_utc"] = pd.to_datetime(
        normalized["signal_time_utc"], utc=True
    )
    paired = [_pair_trade(normalized, trade) for _, trade in trades.iterrows()]
    return tuple(paired)


def _load_baseline(
    path: Path,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    if not path.is_file():
        raise FileNotFoundError(f"maker baseline report does not exist: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("maker baseline report must be a JSON object")
    signals_path = path.with_suffix(".signals.parquet")
    trades_path = path.with_suffix(".trades.parquet")
    for sidecar in (signals_path, trades_path):
        if not sidecar.is_file():
            raise FileNotFoundError(f"maker baseline sidecar does not exist: {sidecar}")
    return raw, pd.read_parquet(signals_path), pd.read_parquet(trades_path)


def _reconstruct_all(
    database_path: Path,
    pairs: tuple[PairedMakerRequest, ...],
    config: MakerEntryConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    entry_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    with duckdb.connect(str(database_path), read_only=True) as connection:
        for pair in pairs:
            books, trades = _entry_events(connection, pair.request, config)
            outcome = reconstruct_maker_entry(pair.request, books, trades, config)
            entry_rows.append(_entry_row(pair, outcome))
            if outcome.status == "filled":
                signal_rows.append(
                    build_maker_replay_signal(
                        pair.request,
                        outcome,
                        candidate=f"{pair.candidate}_maker_bbo_v1",
                    )
                )
    entries = pd.DataFrame(entry_rows)
    signals = pd.DataFrame(signal_rows, columns=_maker_signal_columns())
    return entries, signals


def _entry_events(
    connection: duckdb.DuckDBPyConnection,
    request: MakerEntryRequest,
    config: MakerEntryConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    books = connection.execute(
        """
        SELECT ts_exchange_ms, best_bid, best_ask, bids, asks
        FROM replay_book_snapshots
        WHERE symbol = 'BTC' AND ts_exchange_ms >= ? AND ts_exchange_ms <= ?
        ORDER BY ts_exchange_ms LIMIT 1
        """,
        [
            request.decision_time_ms,
            request.decision_time_ms + config.maximum_book_delay_ms,
        ],
    ).fetchdf()
    if books.empty:
        return books, pd.DataFrame()
    book_time = int(books.iloc[0]["ts_exchange_ms"])
    trades = connection.execute(
        """
        SELECT ts_exchange_ms, aggressor_side, price, size
        FROM public_trades
        WHERE symbol = 'BTC' AND ts_exchange_ms >= ? AND ts_exchange_ms <= ?
        QUALIFY row_number() OVER (
            PARTITION BY symbol, trade_id ORDER BY bundle_id
        ) = 1
        ORDER BY ts_exchange_ms, trade_id
        """,
        [book_time, book_time + config.entry_ttl_seconds * 1_000],
    ).fetchdf()
    return books, trades


def _load_one_minute_bars(
    database_path: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        bars = connection.execute(
            """
            SELECT bar_open_at, open, high, low, close, volume
            FROM canonical_trade_1m_bars
            WHERE symbol = 'BTC' AND bar_open_at >= ? AND bar_open_at < ?
            ORDER BY bar_open_at
            """,
            [start.to_pydatetime(), (end + pd.Timedelta(days=1)).to_pydatetime()],
        ).fetchdf()
    if bars.empty:
        raise ValueError("maker replay has no canonical BTC one-minute bars")
    bars["bar_open_at"] = pd.to_datetime(bars["bar_open_at"], utc=True)
    output = bars.set_index("bar_open_at")
    if not output.index.is_monotonic_increasing or not output.index.is_unique:
        raise ValueError("maker replay bars must be ordered and unique")
    return output


def _entry_row(
    pair: PairedMakerRequest,
    outcome: MakerEntryOutcome,
) -> dict[str, object]:
    row = {
        "baseline_signal_time_utc": pair.signal_time_utc,
        "candidate": pair.candidate,
        "direction": pair.request.direction,
        "quantity": pair.request.quantity,
        "original_entry_price": pair.request.original_entry_price,
        "decision_time_ms": pair.request.decision_time_ms,
    }
    row.update(asdict(outcome))
    return row


def _maker_signal_columns() -> list[str]:
    return [
        "signal_time_utc",
        "symbol",
        "candidate",
        "side",
        "score",
        "stop_anchor",
        "eligible",
        "entry_price_override",
    ]


def _pair_trade(signals: pd.DataFrame, trade: pd.Series) -> PairedMakerRequest:
    signal_time = _timestamp(trade["signal_time_utc"], "trade signal time")
    direction = str(trade["direction"])
    matches = signals.loc[
        signals["signal_time_utc"].eq(signal_time)
        & signals["candidate"].astype(str).eq(str(trade["candidate"]))
        & signals["symbol"].astype(str).eq(str(trade["symbol"]))
        & signals["side"].astype(str).eq(direction)
    ]
    if len(matches) != 1:
        raise ValueError("each baseline trade must match exactly one signal")
    signal = matches.iloc[0]
    request = MakerEntryRequest(
        decision_time_ms=_timestamp_ms(trade["entry_time_utc"]),
        direction=_direction(direction),
        quantity=_positive(trade["initial_quantity"], "baseline quantity"),
        original_entry_price=_positive(trade["entry_price"], "baseline entry"),
        stop_anchor=_positive(signal["stop_anchor"], "baseline stop anchor"),
        signal_score=_finite(signal["score"], "baseline signal score"),
    )
    return PairedMakerRequest(signal_time, str(trade["candidate"]), request)


def _validate_report_identity(
    report: dict[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment: ChronologicalSegment,
) -> None:
    if report.get("schema_version") != "market_cipher_strategy_screen_v3":
        raise ValueError("maker baseline schema is not supported")
    if (
        report.get("report_only") is not True
        or report.get("place_attempted") is not False
    ):
        raise ValueError("maker baseline must be report-only")
    if report.get("execution_authority") != "none":
        raise ValueError("maker baseline must have no execution authority")
    if report.get("bar_minutes") != 15:
        raise ValueError("maker baseline must use the frozen 15-minute signal")
    if report.get("segment") != segment:
        raise ValueError("maker baseline segment does not match the requested segment")
    if _timestamp(report.get("start_utc"), "baseline start") != _utc(start):
        raise ValueError("maker baseline start does not match the requested window")
    if _timestamp(report.get("end_utc"), "baseline end") != _utc(end):
        raise ValueError("maker baseline end does not match the requested window")
    _validate_profile_and_parameters(report)


def _validate_profile_and_parameters(report: dict[str, object]) -> None:
    profile = report.get("profile")
    if not isinstance(profile, dict) or profile.get("name") != _PROFILE:
        raise ValueError("maker baseline profile is not the frozen bidirectional Hulk")
    if profile.get("side") is not None:
        raise ValueError("maker baseline must retain both directions")
    symbols = report.get("symbol_attribution")
    if not isinstance(symbols, dict) or set(symbols) != {"BTC"}:
        raise ValueError("maker baseline report must contain only BTC")
    parameters = report.get("replay_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("maker baseline replay parameters are missing")
    for name, expected in _BASELINE_PARAMETERS.items():
        if parameters.get(name) != expected:
            raise ValueError(f"maker baseline parameter changed: {name}")


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {missing}")


def _direction(value: str) -> Literal["long", "short"]:
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise ValueError("baseline direction must be long or short")


def _timestamp_ms(value: object) -> int:
    return int(_timestamp(value, "baseline entry time").value // 1_000_000)


def _timestamp(value: object, label: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    return _timestamp(value, "requested timestamp")


def _window(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    first, last = _utc(start), _utc(end)
    if first >= last:
        raise ValueError("maker research start must precede end")
    return first, last


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive(value: object, label: str) -> float:
    number = _finite(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number
