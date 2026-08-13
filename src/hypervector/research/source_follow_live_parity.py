"""Read-only parity audit for source-follow live shadow telemetry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math

import pandas as pd


_MISMATCH_LIMIT = 20


@dataclass(frozen=True)
class SourceFollowParityPolicy:
    """Execution-independent policy required to reconstruct live decisions."""

    profile_id: str
    minimum_confidence: float = 0.70
    minimum_range_bps: float = 12.0
    maximum_range_bps: float = 100.0
    decision_delay_seconds: float = 300.0
    entry_pulse_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("source-follow parity profile_id must not be empty")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("source-follow parity confidence must be within [0, 1]")
        if not 0.0 <= self.minimum_range_bps <= self.maximum_range_bps:
            raise ValueError("source-follow parity range bounds are invalid")
        delays = (self.decision_delay_seconds, self.entry_pulse_seconds)
        if not all(math.isfinite(value) and value > 0.0 for value in delays):
            raise ValueError("source-follow parity timing must be finite and positive")


@dataclass(frozen=True)
class LiveCandleAssembly:
    """Completed venue candles reconstructed from warm-up and live telemetry."""

    candles: pd.DataFrame
    appended_rows: int
    trailing_rows_discarded: int


@dataclass(frozen=True)
class _ExpectedState:
    label_time_utc: datetime
    available_at_utc: datetime
    primary: str
    confidence: float
    signal_range_bps: float
    entry_eligible: bool
    exclusion_reason: str | None


def assemble_source_follow_live_candles(
    warmup: pd.DataFrame,
    rows: Sequence[Mapping[str, object]],
    profile_id: str,
) -> LiveCandleAssembly:
    """Extend an aligned warm-up with gap-checked backend one-minute bars."""
    if not profile_id:
        raise ValueError("live candle assembly profile_id must not be empty")
    completed = _normalized_bars(warmup)
    _validate_candle_grid(completed, require_complete_groups=True)
    completed = _with_hyperliquid_source(completed)
    live = _ledger_candles(rows, profile_id, completed.index[-1])
    if live.empty:
        return LiveCandleAssembly(completed, 0, 0)
    combined = pd.concat([completed, live]).sort_index(kind="stable")
    _validate_candle_grid(combined, require_complete_groups=False)
    boundaries = combined.index[combined.index.minute % 5 == 4]
    if boundaries.empty:
        raise ValueError("live candle assembly has no completed five-minute group")
    published = combined.loc[: boundaries[-1]].copy()
    trailing = len(combined) - len(published)
    return LiveCandleAssembly(
        candles=published,
        appended_rows=len(published) - len(completed),
        trailing_rows_discarded=trailing,
    )


def audit_source_follow_live_rows(
    rows: Sequence[Mapping[str, object]],
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    policy: SourceFollowParityPolicy,
) -> dict[str, object]:
    """Compare backend-authored live observations with causal offline evidence."""
    observations = [
        row
        for row in rows
        if row.get("action") == "regime_observation"
        and row.get("profile_id") == policy.profile_id
    ]
    if not observations:
        return _empty_report(policy)
    normalized_labels = _normalized_labels(labels)
    normalized_bars = _normalized_bars(bars)
    expected = _expected_states(normalized_labels, normalized_bars, policy)
    mismatches: list[dict[str, object]] = []
    uncovered: list[dict[str, object]] = []
    mismatch_count = 0
    covered = 0
    for position, row in enumerate(observations):
        outcome = _audit_observation(position, row, expected, policy)
        if outcome["kind"] == "uncovered":
            if len(uncovered) < _MISMATCH_LIMIT:
                uncovered.append(outcome["detail"])
            continue
        covered += 1
        if outcome["kind"] == "mismatch":
            mismatch_count += 1
            if len(mismatches) < _MISMATCH_LIMIT:
                mismatches.append(outcome["detail"])
    submitted_true = sum(row.get("submitted") is True for row in observations)
    placed_true = sum(row.get("place_attempted") is True for row in observations)
    uncovered_count = len(observations) - covered
    exact = not mismatch_count and not uncovered_count and not submitted_true
    exact = exact and not placed_true
    return {
        "report_only": True,
        "execution_authority": "none",
        "profile_id": policy.profile_id,
        "observations": len(observations),
        "covered_observations": covered,
        "mismatch_count": mismatch_count,
        "uncovered_count": uncovered_count,
        "submitted_true": submitted_true,
        "place_attempted_true": placed_true,
        "mismatches": mismatches,
        "uncovered": uncovered,
        "exact": exact,
        "failure_reason": None
        if exact
        else _failure_reason(mismatch_count, uncovered_count),
    }


def _empty_report(policy: SourceFollowParityPolicy) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "profile_id": policy.profile_id,
        "observations": 0,
        "covered_observations": 0,
        "mismatch_count": 0,
        "uncovered_count": 0,
        "submitted_true": 0,
        "place_attempted_true": 0,
        "mismatches": [],
        "uncovered": [],
        "exact": False,
        "failure_reason": "no_matching_regime_observations",
    }


def _ledger_candles(
    rows: Sequence[Mapping[str, object]],
    profile_id: str,
    after: pd.Timestamp,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in rows:
        if row.get("action") != "regime_observation":
            continue
        if row.get("profile_id") != profile_id:
            continue
        opened = pd.Timestamp(_utc_datetime(row.get("feed_ts"), "ledger feed_ts"))
        opened -= pd.Timedelta(minutes=1)
        if opened <= after:
            continue
        records.append(_ledger_candle_record(row, opened))
    if not records:
        return _empty_candle_frame()
    frame = pd.DataFrame.from_records(records).set_index("timestamp")
    frame.index = pd.DatetimeIndex(frame.index)
    if not frame.index.is_unique:
        raise ValueError("live candle ledger contains duplicate one-minute timestamps")
    return frame.sort_index(kind="stable")


def _ledger_candle_record(
    row: Mapping[str, object],
    opened: pd.Timestamp,
) -> dict[str, object]:
    opening = _finite_float(row.get("open"), "ledger candle open")
    high = _finite_float(row.get("high"), "ledger candle high")
    low = _finite_float(row.get("low"), "ledger candle low")
    close = _finite_float(row.get("mark_px"), "ledger candle close")
    volume = _finite_float(row.get("volume"), "ledger candle volume")
    if opening <= 0.0 or close <= 0.0 or volume < 0.0:
        raise ValueError("ledger candle prices and volume are invalid")
    if high < max(opening, close, low) or low > min(opening, close, high):
        raise ValueError("ledger candle has inconsistent OHLC values")
    return {
        "timestamp": opened,
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": "hl_shadow_ledger",
    }


def _empty_candle_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["open", "high", "low", "close", "volume", "source"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )


def _with_hyperliquid_source(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "source" not in result.columns:
        result["source"] = "hl"
    if not result["source"].astype(str).str.startswith("hl").all():
        raise ValueError("live candle warm-up contains a non-Hyperliquid source")
    return result


def _validate_candle_grid(
    frame: pd.DataFrame,
    *,
    require_complete_groups: bool,
) -> None:
    if frame.empty:
        raise ValueError("live candle assembly requires warm-up candles")
    if frame.index.second.any() or frame.index.microsecond.any():
        raise ValueError("live candles must be minute-aligned")
    cadence = frame.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("live candles require contiguous one-minute candles")
    if require_complete_groups and (
        frame.index[0].minute % 5 or frame.index[-1].minute % 5 != 4 or len(frame) % 5
    ):
        raise ValueError("warm-up requires complete aligned five-minute groups")


def _expected_states(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    policy: SourceFollowParityPolicy,
) -> tuple[_ExpectedState, ...]:
    states: list[_ExpectedState] = []
    previous_primary: str | None = None
    for stamp, row in labels.iterrows():
        timestamp = _utc_datetime(stamp, "source label timestamp")
        primary = str(row["primary_code"])
        confidence = _finite_float(row["confidence"], "source confidence")
        bar = bars.loc[stamp] if stamp in bars.index else None
        if bar is not None:
            range_bps = _bar_range_bps(bar)
            onset = primary != previous_primary
            exclusion = _exclusion(primary, confidence, onset, range_bps, policy)
            states.append(
                _ExpectedState(
                    label_time_utc=timestamp,
                    available_at_utc=_available_at(timestamp, row, policy),
                    primary=primary,
                    confidence=confidence,
                    signal_range_bps=range_bps,
                    entry_eligible=exclusion is None,
                    exclusion_reason=exclusion,
                )
            )
        previous_primary = primary
    return tuple(states)


def _audit_observation(
    position: int,
    row: Mapping[str, object],
    states: tuple[_ExpectedState, ...],
    policy: SourceFollowParityPolicy,
) -> dict[str, object]:
    feed = _utc_datetime(row.get("feed_ts"), "ledger feed_ts")
    label = _utc_datetime(
        row.get("source_follow_label_time_utc"),
        "ledger source_follow_label_time_utc",
    )
    available = [state for state in states if state.available_at_utc <= feed]
    claimed = next((state for state in states if state.label_time_utc == label), None)
    if claimed is None or not available:
        return {
            "kind": "uncovered",
            "detail": {
                "row_position": position,
                "feed_ts": feed.isoformat(),
                "label_time_utc": label.isoformat(),
                "reason": "offline_label_or_bar_unavailable",
            },
        }
    expected = available[-1]
    fields = _mismatched_fields(row, expected, feed, policy)
    if fields:
        return {
            "kind": "mismatch",
            "detail": {
                "row_position": position,
                "feed_ts": feed.isoformat(),
                "label_time_utc": label.isoformat(),
                "fields": fields,
            },
        }
    return {"kind": "exact", "detail": {}}


def _mismatched_fields(
    row: Mapping[str, object],
    state: _ExpectedState,
    feed: datetime,
    policy: SourceFollowParityPolicy,
) -> dict[str, object]:
    pulse_until = state.available_at_utc + timedelta(seconds=policy.entry_pulse_seconds)
    direction = (
        "short"
        if state.entry_eligible and state.available_at_utc <= feed < pulse_until
        else None
    )
    reason = (
        "source_follow_entry_pulse"
        if state.entry_eligible
        else f"source_follow_{state.exclusion_reason}"
    )
    expected: dict[str, object] = {
        "source_follow_label_time_utc": state.label_time_utc,
        "source_follow_available_at_utc": state.available_at_utc,
        "primary_regime": state.primary,
        "state_5m": state.primary,
        "confidence": state.confidence,
        "source_follow_signal_range_bps": state.signal_range_bps,
        "entry_direction": direction,
        "structural_direction": direction,
        "entry_allowed": direction is not None,
        "regime_reason": reason,
        "submitted": False,
        "place_attempted": False,
    }
    return {
        field: {"expected": _serializable(value), "actual": row.get(field)}
        for field, value in expected.items()
        if not _equal_field(field, row.get(field), value)
    }


def _equal_field(field: str, actual: object, expected: object) -> bool:
    if field.endswith("_utc"):
        try:
            return _utc_datetime(actual, field) == expected
        except (TypeError, ValueError):
            return False
    if field in {"confidence", "source_follow_signal_range_bps"}:
        try:
            value = float(actual)
        except (TypeError, ValueError):
            return False
        return math.isclose(value, float(expected), rel_tol=0.0, abs_tol=1e-10)
    return actual == expected


def _normalized_labels(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"primary_code", "secondary_code", "confidence"}
    return _normalized_frame(frame, required, "source labels")


def _normalized_bars(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    return _normalized_frame(frame, required, "source bars")


def _normalized_frame(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f"{label} require a DatetimeIndex")
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")
    result = frame.copy()
    result.index = pd.DatetimeIndex(pd.to_datetime(result.index, utc=True))
    if not result.index.is_monotonic_increasing or not result.index.is_unique:
        raise ValueError(f"{label} timestamps must be ordered and unique")
    return result


def _bar_range_bps(row: pd.Series) -> float:
    opening = _finite_float(row["open"], "source bar open")
    high = _finite_float(row["high"], "source bar high")
    low = _finite_float(row["low"], "source bar low")
    if opening <= 0.0 or high < low:
        raise ValueError("source bar has invalid OHLC values")
    return 10_000.0 * (high - low) / opening


def _available_at(
    stamp: datetime,
    row: pd.Series,
    policy: SourceFollowParityPolicy,
) -> datetime:
    value = row.get("available_at")
    if value is not None and not pd.isna(value):
        return _utc_datetime(value, "source available_at")
    return stamp + timedelta(seconds=policy.decision_delay_seconds)


def _exclusion(
    primary: str,
    confidence: float,
    onset: bool,
    range_bps: float,
    policy: SourceFollowParityPolicy,
) -> str | None:
    if not onset:
        return "not_primary_onset"
    if primary != "TREND_DOWN":
        return "primary_not_trend_down"
    if confidence < policy.minimum_confidence:
        return "source_confidence"
    if range_bps < policy.minimum_range_bps:
        return "signal_range_below_minimum"
    if range_bps > policy.maximum_range_bps:
        return "signal_range"
    return None


def _utc_datetime(value: object, label: str) -> datetime:
    if value is None:
        raise ValueError(f"{label} is missing")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.tz_convert("UTC").to_pydatetime().astimezone(UTC)


def _finite_float(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _serializable(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


def _failure_reason(mismatches: int, uncovered: int) -> str:
    if mismatches and uncovered:
        return "mismatches_and_missing_offline_evidence"
    if mismatches:
        return "live_offline_mismatch"
    return "missing_offline_evidence"
