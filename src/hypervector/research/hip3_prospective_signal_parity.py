"""Report-only HIP-3 signal parity across prospective candle sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import pandas as pd

from hypervector.data.hl_events import L2SnapshotEvent
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)

_DECISION_DELAY_MS = 15_000
_PRESSURE_SOURCE = "hyperliquid_ws_l2Book"
_PRICE_TOLERANCE = 1e-9
_TIMEFRAME_MINUTES = 15
_TIMEFRAME_MS = _TIMEFRAME_MINUTES * 60_000


@dataclass(frozen=True)
class Hip3ProspectiveSignalParityConfig:
    """Frozen HIP-3 route identity and breakout-pressure parameters."""

    symbol: str
    provider_id: str
    profile_id: str
    breakout: Hip3BreakoutPressureConfig
    timeframe: str = "15m"

    def __post_init__(self) -> None:
        """Reject aliased or unsupported prospective route identities."""
        validate_market_symbol(self.symbol, "hip3")
        if not self.provider_id.strip() or not self.profile_id.strip():
            raise ValueError("prospective signal parity requires route identity")
        if self.timeframe != "15m":
            raise ValueError("prospective signal parity currently requires 15m")


def build_hip3_prospective_signal_parity(
    *,
    trade_bars: pd.DataFrame,
    venue_bars: pd.DataFrame,
    l2_snapshots: tuple[L2SnapshotEvent, ...],
    observed_at_ms: int,
    config: Hip3ProspectiveSignalParityConfig,
) -> dict[str, object]:
    """Measure whether two OHLC sources produce identical route decisions."""
    _validate_observed_at(observed_at_ms)
    trade = _validated_bars(trade_bars, observed_at_ms, "trade")
    venue = _validated_bars(venue_bars, observed_at_ms, "venue")
    if not trade.index.equals(venue.index):
        raise ValueError("prospective signal parity bar indexes differ")
    pressure, pressure_rows = _pressure_series(
        trade.index, l2_snapshots, observed_at_ms, config.symbol
    )
    trade_signals = _signals(trade, pressure, config.breakout)
    venue_signals = _signals(venue, pressure, config.breakout)
    ready_start = _ready_start(config.breakout)
    diagnostics = _diagnostics(trade_signals, venue_signals, ready_start)
    coverage = _coverage(
        trade_signals, venue_signals, pressure_rows, diagnostics, ready_start
    )
    entry_events = {
        "trade": _entry_events(trade_signals, ready_start),
        "venue": _entry_events(venue_signals, ready_start),
    }
    pressure_decisions = _pressure_decisions(pressure_rows, ready_start)
    return _report(
        config, l2_snapshots, coverage, diagnostics, entry_events, pressure_decisions
    )


def _validated_bars(
    bars: pd.DataFrame, observed_at_ms: int, label: str
) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"{label} signal bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError(f"{label} signal bars require timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError(f"{label} signal bars require ordered unique rows")
    frame = bars.loc[:, ["open", "high", "low", "close"]].astype(float).copy()
    _validate_prices(frame, label)
    _validate_cadence(frame.index, observed_at_ms, label)
    return frame


def _validate_prices(frame: pd.DataFrame, label: str) -> None:
    if not frame.map(math.isfinite).to_numpy().all() or frame.le(0.0).any().any():
        raise ValueError(f"{label} signal OHLC must be finite and positive")
    if frame["high"].lt(frame[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError(f"{label} signal highs are inconsistent")
    if frame["low"].gt(frame[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"{label} signal lows are inconsistent")


def _validate_cadence(index: pd.DatetimeIndex, observed_at_ms: int, label: str) -> None:
    timestamps = index.as_unit("ms").astype("int64")
    if any(int(value) % _TIMEFRAME_MS for value in timestamps):
        raise ValueError(f"{label} signal bars are not 15m aligned")
    if (
        len(timestamps) > 1
        and not pd.Series(timestamps).diff().iloc[1:].eq(_TIMEFRAME_MS).all()
    ):
        raise ValueError(f"{label} signal bars are not contiguous")
    if int(timestamps[-1]) + _TIMEFRAME_MS > observed_at_ms:
        raise ValueError(f"{label} signal bars include an incomplete interval")


def _pressure_series(
    index: pd.DatetimeIndex,
    snapshots: tuple[L2SnapshotEvent, ...],
    observed_at_ms: int,
    symbol: str,
) -> tuple[pd.Series, tuple[dict[str, object], ...]]:
    values: list[float] = []
    evidence: list[dict[str, object]] = []
    for timestamp in index:
        bar_open = _timestamp_ms(timestamp)
        row = _bar_pressure(snapshots, bar_open, observed_at_ms, symbol)
        values.append(float(row["imbalance_10"]) if row["fresh"] else 0.0)
        evidence.append(row)
    return pd.Series(values, index=index, dtype=float), tuple(evidence)


def _bar_pressure(
    snapshots: tuple[L2SnapshotEvent, ...],
    bar_open_ms: int,
    observed_at_ms: int,
    symbol: str,
) -> dict[str, object]:
    bar_close = bar_open_ms + _TIMEFRAME_MS
    receipt_cutoff = min(observed_at_ms, bar_close + _DECISION_DELAY_MS)
    eligible = tuple(
        row
        for row in snapshots
        if bar_open_ms <= row.exchange_ts_ms < bar_close
        and row.received_ts_ns // 1_000_000 <= receipt_cutoff
    )
    canonical = _canonical_books(eligible, symbol)
    last = canonical[-1] if canonical else None
    age = None if last is None else bar_close - last.exchange_ts_ms
    fresh = len(canonical) >= 2 and age is not None and age <= _DECISION_DELAY_MS
    return {
        "bar_open_ms": bar_open_ms,
        "snapshot_count": len(canonical),
        "last_exchange_ts_ms": None if last is None else last.exchange_ts_ms,
        "end_boundary_age_ms": age,
        "imbalance_10": None if last is None else _imbalance_10(last),
        "fresh": fresh,
    }


def _canonical_books(
    snapshots: tuple[L2SnapshotEvent, ...], symbol: str
) -> tuple[L2SnapshotEvent, ...]:
    selected: dict[int, L2SnapshotEvent] = {}
    for snapshot in snapshots:
        if snapshot.symbol != symbol or snapshot.source != _PRESSURE_SOURCE:
            raise ValueError("prospective signal L2 identity is inconsistent")
        _validate_book(snapshot)
        previous = selected.get(snapshot.exchange_ts_ms)
        if previous is not None and previous.event_key != snapshot.event_key:
            raise ValueError("conflicting L2 exchange timestamp")
        if previous is None or snapshot.received_ts_ns < previous.received_ts_ns:
            selected[snapshot.exchange_ts_ms] = snapshot
    return tuple(selected[key] for key in sorted(selected))


def _validate_book(snapshot: L2SnapshotEvent) -> None:
    if len(snapshot.bids) < 10 or len(snapshot.asks) < 10:
        raise ValueError("prospective signal L2 requires ten levels per side")
    bid_prices = tuple(level.price for level in snapshot.bids[:10])
    ask_prices = tuple(level.price for level in snapshot.asks[:10])
    bids_ordered = all(left > right for left, right in zip(bid_prices, bid_prices[1:]))
    asks_ordered = all(left < right for left, right in zip(ask_prices, ask_prices[1:]))
    if not bids_ordered or not asks_ordered or bid_prices[0] >= ask_prices[0]:
        raise ValueError("prospective signal L2 must be ordered and non-crossed")


def _imbalance_10(snapshot: L2SnapshotEvent) -> float:
    bid = sum(level.size for level in snapshot.bids[:10])
    ask = sum(level.size for level in snapshot.asks[:10])
    return (bid - ask) / (bid + ask)


def _signals(
    bars: pd.DataFrame,
    pressure: pd.Series,
    config: Hip3BreakoutPressureConfig,
) -> pd.DataFrame:
    inputs = bars.copy()
    inputs["decision_imbalance_10"] = pressure
    inputs["gap_before_bars"] = 0
    return build_breakout_pressure_signals(inputs, config, timeframe="15m")


def _ready_start(config: Hip3BreakoutPressureConfig) -> int:
    return max(config.slow_ema - 1, config.breakout_lookback_bars)


def _diagnostics(
    trade: pd.DataFrame, venue: pd.DataFrame, ready_start: int
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for position in range(ready_start, len(trade)):
        fields = _mismatched_fields(trade.iloc[position], venue.iloc[position])
        if fields:
            output.append(
                {
                    "bar_open_ms": _timestamp_ms(trade.index[position]),
                    "mismatched_fields": fields,
                }
            )
    return output


def _mismatched_fields(trade: pd.Series, venue: pd.Series) -> list[str]:
    fields = [
        name
        for name in ("long_entry", "short_entry", "long_exit", "short_exit")
        if bool(trade[name]) != bool(venue[name])
    ]
    same_entry = bool(trade["long_entry"]) == bool(venue["long_entry"]) and bool(
        trade["short_entry"]
    ) == bool(venue["short_entry"])
    if same_entry and _different_stop(trade["stop_price"], venue["stop_price"]):
        fields.append("stop_price")
    return fields


def _different_stop(left: object, right: object) -> bool:
    left_value, right_value = float(left), float(right)
    if math.isnan(left_value) and math.isnan(right_value):
        return False
    return not math.isclose(
        left_value, right_value, rel_tol=0.0, abs_tol=_PRICE_TOLERANCE
    )


def _coverage(
    trade: pd.DataFrame,
    venue: pd.DataFrame,
    pressure: tuple[dict[str, object], ...],
    diagnostics: list[dict[str, object]],
    ready_start: int,
) -> dict[str, object]:
    ready = pressure[ready_start:]
    decision_index = trade.index[ready_start:]
    decision_start = (
        None
        if decision_index.empty
        else _timestamp_ms(decision_index[0]) + _TIMEFRAME_MS
    )
    decision_end = (
        None
        if decision_index.empty
        else _timestamp_ms(decision_index[-1]) + _TIMEFRAME_MS
    )
    entry_fields = {"long_entry", "short_entry"}
    exit_fields = {"long_exit", "short_exit"}
    events = _signal_event_coverage(trade, venue, ready_start)
    coverage = {
        "completed_bars": len(trade),
        "required_warmup_bars": ready_start + 1,
        "warmup_complete": len(trade) > ready_start,
        "decision_bars": max(len(trade) - ready_start, 0),
        "decision_start_ms": decision_start,
        "decision_end_ms": decision_end,
        "fresh_pressure_decision_bars": sum(bool(row["fresh"]) for row in ready),
        "entry_disagreement_bars": _field_count(diagnostics, entry_fields),
        "exit_disagreement_bars": _field_count(diagnostics, exit_fields),
        "stop_disagreement_bars": _field_count(diagnostics, {"stop_price"}),
    }
    return coverage | events


def _signal_event_coverage(
    trade: pd.DataFrame, venue: pd.DataFrame, ready_start: int
) -> dict[str, int]:
    fields = ("long_entry", "short_entry", "long_exit", "short_exit")
    ready_trade = trade.iloc[ready_start:]
    ready_venue = venue.iloc[ready_start:]
    eventful = ready_trade.loc[:, fields].any(axis=1) | ready_venue.loc[:, fields].any(
        axis=1
    )
    return {
        "eventful_decision_bars": int(eventful.sum()),
        "trade_entry_events": int(ready_trade.loc[:, fields[:2]].sum().sum()),
        "venue_entry_events": int(ready_venue.loc[:, fields[:2]].sum().sum()),
        "trade_exit_events": int(ready_trade.loc[:, fields[2:]].sum().sum()),
        "venue_exit_events": int(ready_venue.loc[:, fields[2:]].sum().sum()),
    }


def _entry_events(signals: pd.DataFrame, ready_start: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for position in range(ready_start, len(signals)):
        bar_open_ms = _timestamp_ms(signals.index[position])
        for field, side in (("long_entry", "long"), ("short_entry", "short")):
            if bool(signals.iloc[position][field]):
                events.append(
                    {
                        "bar_open_ms": bar_open_ms,
                        "decision_time_ms": bar_open_ms + _TIMEFRAME_MS,
                        "side": side,
                    }
                )
    return events


def _pressure_decisions(
    rows: tuple[dict[str, object], ...], ready_start: int
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows[ready_start:]:
        decision = dict(row)
        decision["decision_time_ms"] = int(row["bar_open_ms"]) + _TIMEFRAME_MS
        output.append(decision)
    return output


def _field_count(rows: list[dict[str, object]], names: set[str]) -> int:
    return sum(bool(names.intersection(row["mismatched_fields"])) for row in rows)


def _report(
    config: Hip3ProspectiveSignalParityConfig,
    snapshots: tuple[L2SnapshotEvent, ...],
    coverage: dict[str, object],
    diagnostics: list[dict[str, object]],
    entry_events: dict[str, list[dict[str, object]]],
    pressure_decisions: list[dict[str, object]],
) -> dict[str, object]:
    unresolved = int(coverage["decision_bars"]) - int(
        coverage["fresh_pressure_decision_bars"]
    )
    resolved = bool(coverage["warmup_complete"]) and not diagnostics and not unresolved
    non_vacuous = (
        resolved
        and int(coverage["trade_entry_events"]) > 0
        and int(coverage["venue_entry_events"]) > 0
    )
    return {
        "schema_version": "hip3_prospective_signal_parity_v1",
        "contract": _contract(),
        "scope": asdict(config),
        "source": {
            "pressure_source": _PRESSURE_SOURCE,
            "l2_snapshot_rows": len(snapshots),
            "l2_snapshot_sha256": _l2_hash(snapshots),
        },
        "coverage": coverage,
        "reconstructed_entry_events": entry_events,
        "reconstructed_pressure_decisions": pressure_decisions,
        "signal_diagnostics": diagnostics,
        "technical_assessment": {
            "prospective_signal_source_parity_resolved": resolved,
            "prospective_entry_signal_parity_non_vacuous": non_vacuous,
            "unresolved_pressure_bars": unresolved,
            "signal_disagreement_bars": len(diagnostics),
        },
        "limitations": [
            "signal-source parity does not establish strategy profitability",
            "pressure is receipt-censored at fifteen seconds after each bar close",
            "this report grants no execution or promotion authority",
        ],
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }


def _l2_hash(snapshots: tuple[L2SnapshotEvent, ...]) -> str:
    rows = sorted(
        json.dumps(asdict(snapshot), sort_keys=True, separators=(",", ":"))
        for snapshot in snapshots
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _validate_observed_at(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("observed_at_ms must be a positive integer")


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.as_unit("ms").asm8.astype("int64"))
