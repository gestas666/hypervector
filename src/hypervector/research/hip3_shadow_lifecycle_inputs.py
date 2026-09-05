"""Exact input reconstruction for report-only HIP-3 shadow lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import cast

import pandas as pd

from hypervector.data.hip3_mark_snapshot_recorder import HIP3_REST_MARK_SOURCE
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_prospective_path_audit import hip3_bar_path_quality
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowBook,
    Hip3ShadowDecision,
    validated_shadow_books,
    validated_shadow_decisions,
)
from hypervector.research.hip3_transfer_sources import (
    FundingAttachmentEvidence,
    attach_official_funding,
    validated_official_funding,
)

INTERVAL_MS = 15 * 60_000
_CANDLE_SOURCE = "hl"
HIP3_EXACT_MARK_SOURCE = "hyperliquid_ws_activeAssetCtx"
HIP3_EXACT_MARK_SOURCES = {
    HIP3_EXACT_MARK_SOURCE,
    HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
}
_MARK_SOURCES = HIP3_EXACT_MARK_SOURCES | {HIP3_REST_MARK_SOURCE}


@dataclass(frozen=True)
class Hip3ShadowMark:
    """One locally timestamped public mark observation."""

    receipt_ns: int
    timestamp_ms: int
    price: float
    source: str


@dataclass(frozen=True)
class Hip3ShadowLifecycleInputs:
    """Validated causal inputs consumed by both replay variants."""

    decisions: tuple[Hip3ShadowDecision, ...]
    books: tuple[Hip3ShadowBook, ...]
    marks: tuple[Hip3ShadowMark, ...]
    signals: pd.DataFrame
    publication: dict[int, int]
    funding: pd.DataFrame
    funding_evidence: FundingAttachmentEvidence
    signal_bars: pd.DataFrame


def prepare_shadow_lifecycle_inputs(
    *,
    decision_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    candles: pd.DataFrame,
    mark_rows: Sequence[Mapping[str, object]],
    funding_rows: pd.DataFrame,
    config: Hip3ShadowLifecycleConfig,
) -> Hip3ShadowLifecycleInputs:
    """Validate exact sources and reproduce the prospective signal journal."""
    decisions = validated_shadow_decisions(decision_rows, config)
    books = validated_shadow_books(book_rows, config)
    pressure, publication = _decision_state(decision_rows, config)
    bars = _signal_bars(candles, pressure, config)
    signals = build_breakout_pressure_signals(bars, config.signal_config)
    _reconcile_onsets(decisions, signals)
    _funded_bars, evidence = attach_official_funding(
        bars.loc[:, ["open", "high", "low", "close"]], funding_rows
    )
    funding = validated_official_funding(funding_rows)
    return Hip3ShadowLifecycleInputs(
        decisions,
        books,
        _marks(mark_rows, config),
        signals,
        publication,
        funding,
        evidence,
        bars,
    )


def mark_path_resolved(
    marks: Sequence[Hip3ShadowMark],
    start_ms: int,
    end_ms: int,
    maximum_gap_ms: int,
) -> bool:
    """Return true only for complete boundary-aware post-entry mark evidence."""
    if end_ms <= start_ms:
        return False
    timestamps = [
        mark.timestamp_ms
        for mark in marks
        if mark.source in HIP3_EXACT_MARK_SOURCES
        and start_ms <= mark.timestamp_ms <= end_ms
    ]
    quality = hip3_bar_path_quality(
        timestamps,
        start_ms=start_ms,
        end_ms=end_ms + 1,
        maximum_gap_ms=maximum_gap_ms,
    )
    return quality["complete"] is True


def _decision_state(
    rows: Sequence[Mapping[str, object]], config: Hip3ShadowLifecycleConfig
) -> tuple[dict[int, float], dict[int, int]]:
    pressure: dict[int, float] = {}
    publication: dict[int, int] = {}
    seen: set[str] = set()
    for row in rows:
        event_id = _text(row.get("event_id"), "decision event id")
        if event_id in seen:
            raise ValueError("HIP-3 lifecycle contains a duplicate decision")
        seen.add(event_id)
        decision = _mapping(row.get("decision"), "decision")
        _require_decision_row(row, decision, config)
        decision_ms = _integer(decision.get("decision_time_ms"), "decision time")
        observed_ms = _integer(decision.get("observed_at_ms"), "observed time")
        if not 0 <= observed_ms - decision_ms <= 15_000:
            raise ValueError("HIP-3 lifecycle decision publication is not causal")
        pressure[decision_ms] = _bounded_number(
            decision.get("decision_imbalance_10"), "decision pressure", -1.0, 1.0
        )
        publication[decision_ms] = observed_ms
    return pressure, publication


def _require_decision_row(
    row: Mapping[str, object],
    decision: Mapping[str, object],
    config: Hip3ShadowLifecycleConfig,
) -> None:
    token = config.symbol.removeprefix("xyz:").lower()
    if row.get("event_type") != f"{token}_hip3_breakout_shadow_decision":
        raise ValueError("HIP-3 lifecycle decision event type is inconsistent")
    report_only = (
        row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
        and row.get("intents") == []
    )
    expected = (config.symbol, config.provider_id, config.profile_id, "none")
    actual = tuple(
        decision.get(name)
        for name in ("symbol", "provider_id", "profile_id", "execution_authority")
    )
    if not report_only or actual != expected or decision.get("prospective") is not True:
        raise ValueError("HIP-3 lifecycle decision authority or identity is invalid")


def _signal_bars(
    candles: pd.DataFrame,
    pressure: Mapping[int, float],
    config: Hip3ShadowLifecycleConfig,
) -> pd.DataFrame:
    frame = _candles(candles)
    decision_times = [value + INTERVAL_MS for value in _epoch_ms(frame.index)]
    observed = [timestamp in pressure for timestamp in decision_times]
    frame["decision_imbalance_10"] = [
        pressure.get(timestamp, 0.0) for timestamp in decision_times
    ]
    elapsed = frame.index.to_series().diff().dt.total_seconds().div(900).fillna(1)
    if elapsed.lt(1).any() or not elapsed.mod(1).eq(0).all():
        raise ValueError("HIP-3 lifecycle candle cadence is invalid")
    frame["gap_before_bars"] = elapsed.sub(1).astype(int)
    required = (
        max(
            config.signal_config.slow_ema,
            config.signal_config.breakout_lookback_bars,
        )
        + 2
    )
    if len(frame) < required:
        raise ValueError("HIP-3 lifecycle has insufficient signal warmup")
    frame.attrs["unobserved_pressure_bars"] = observed.count(False)
    return frame


def _candles(candles: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "source"}
    missing = sorted(required.difference(candles.columns))
    if missing:
        raise ValueError(f"HIP-3 lifecycle candles missing columns: {missing}")
    if set(candles["source"].astype(str)) != {_CANDLE_SOURCE}:
        raise ValueError("HIP-3 lifecycle candle source must be exact Hyperliquid data")
    frame = candles.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("HIP-3 lifecycle candles contain duplicate timestamps")
    frame = frame.sort_values("timestamp").set_index("timestamp")
    if any(value % INTERVAL_MS for value in _epoch_ms(frame.index)):
        raise ValueError("HIP-3 lifecycle candles are not 15m aligned")
    return frame.astype(float)


def _reconcile_onsets(
    decisions: Sequence[Hip3ShadowDecision], signals: pd.DataFrame
) -> None:
    computed = {
        _timestamp_ms(timestamp) + INTERVAL_MS: str(row.entry_direction)
        for timestamp, row in signals.iterrows()
        if bool(row.long_entry) or bool(row.short_entry)
    }
    journal = {decision.decision_time_ms: decision.side for decision in decisions}
    if computed != journal:
        raise ValueError(
            "HIP-3 lifecycle computed onsets do not match the prospective journal"
        )


def _marks(
    rows: Sequence[Mapping[str, object]], config: Hip3ShadowLifecycleConfig
) -> tuple[Hip3ShadowMark, ...]:
    output: dict[int, Hip3ShadowMark] = {}
    for row in rows:
        valid = (
            row.get("symbol") == config.symbol and row.get("source") in _MARK_SOURCES
        )
        if not valid:
            raise ValueError("HIP-3 lifecycle mark identity is inconsistent")
        timestamp = _integer(row.get("observed_ts_ms"), "mark time")
        receipt_ns = _integer(row.get("received_ts_ns"), "mark receipt")
        if receipt_ns // 1_000_000 != timestamp:
            raise ValueError("HIP-3 lifecycle mark timestamp is not its local receipt")
        causal_ms = (receipt_ns + 999_999) // 1_000_000
        mark = Hip3ShadowMark(
            receipt_ns,
            causal_ms,
            _positive_number(row.get("mark_price"), "mark price"),
            _text(row.get("source"), "mark source"),
        )
        prior = output.get(receipt_ns)
        if prior is not None and prior != mark:
            raise ValueError("HIP-3 lifecycle contains conflicting mark observations")
        output[receipt_ns] = mark
    return tuple(sorted(output.values(), key=lambda value: value.receipt_ns))


def _epoch_ms(index: pd.DatetimeIndex) -> list[int]:
    return list(index.as_unit("ns").asi8 // 1_000_000)


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.as_unit("ns").value // 1_000_000)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 lifecycle {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HIP-3 lifecycle {label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HIP-3 lifecycle {label} must be a nonnegative integer")
    return value


def _positive_number(value: object, label: str) -> float:
    result = _bounded_number(value, label, 0.0, math.inf)
    if result == 0.0:
        raise ValueError(f"HIP-3 lifecycle {label} must be positive")
    return result


def _bounded_number(value: object, label: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 lifecycle {label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"HIP-3 lifecycle {label} is outside its valid bounds")
    return result
