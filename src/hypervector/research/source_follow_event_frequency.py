"""Causal signal-frequency audit for the pinned source-follow policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

import pandas as pd


Direction = Literal["long", "short"]


@dataclass(frozen=True)
class SourceFollowFrequencyPolicy:
    """Frozen event qualifications whose cadence is being measured."""

    minimum_confidence: float = 0.70
    minimum_range_bps: float = 12.0
    maximum_range_bps: float = 100.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.minimum_confidence) or not (
            0.0 <= self.minimum_confidence <= 1.0
        ):
            raise ValueError("minimum confidence must be within [0, 1]")
        ranges = (self.minimum_range_bps, self.maximum_range_bps)
        if not all(math.isfinite(value) and value >= 0.0 for value in ranges):
            raise ValueError("range bounds must be finite and non-negative")
        if self.minimum_range_bps > self.maximum_range_bps:
            raise ValueError("minimum range must not exceed maximum range")


def audit_source_follow_event_frequency(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    policy: SourceFollowFrequencyPolicy,
    *,
    trailing_days: tuple[int, ...] = (7, 14, 30, 60, 90),
) -> dict[str, object]:
    """Count causal qualified onsets without simulating orders or returns."""
    windows = _validated_windows(trailing_days)
    frame = _event_frame(labels, bars, policy)
    events = frame.loc[frame["eligible"]].copy()
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "policy": asdict(policy),
        "bars": len(frame),
        "start_utc": frame.index[0].isoformat(),
        "end_utc": frame.index[-1].isoformat(),
        "source_events_before_range": int(frame["source_event"].sum()),
        "eligible_events": len(events),
        "excluded_below_minimum_range": _excluded(frame, "below_minimum"),
        "excluded_above_maximum_range": _excluded(frame, "above_maximum"),
        "by_direction": _counts(events, "direction"),
        "by_primary": _counts(events, "primary"),
        "trailing": _trailing(events, frame.index[-1], windows),
        "gap_hours": _gap_summary(events),
        "events": _event_rows(events),
        "limitations": _limitations(),
    }


def _event_frame(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    policy: SourceFollowFrequencyPolicy,
) -> pd.DataFrame:
    _validate_frame(labels, "source labels")
    _validate_frame(bars, "five-minute bars")
    _require_columns(
        labels,
        {"available_at", "primary_code", "secondary_code", "confidence"},
        "source labels",
    )
    _require_columns(bars, {"open", "high", "low", "close", "volume"}, "bars")
    missing = bars.index.difference(labels.index)
    if len(missing):
        raise ValueError("source labels do not cover every five-minute bar")
    selected = labels.reindex(bars.index)
    available = pd.DatetimeIndex(pd.to_datetime(selected["available_at"], utc=True))
    expected = bars.index + pd.Timedelta(minutes=5)
    if not available.equals(expected):
        raise ValueError("source label availability must be five minutes causal")
    return _classified_frame(selected, bars, available, policy)


def _classified_frame(
    labels: pd.DataFrame,
    bars: pd.DataFrame,
    available: pd.DatetimeIndex,
    policy: SourceFollowFrequencyPolicy,
) -> pd.DataFrame:
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    secondary = labels["secondary_code"].fillna("").astype(str).str.upper()
    confidence = pd.to_numeric(labels["confidence"], errors="raise")
    direction = _directions(primary, secondary)
    previous = primary.shift(1)
    onset = previous.notna() & primary.ne(previous)
    range_bps = _range_bps(bars)
    source_event = onset & direction.notna() & confidence.ge(policy.minimum_confidence)
    below = source_event & range_bps.lt(policy.minimum_range_bps)
    above = source_event & range_bps.gt(policy.maximum_range_bps)
    return pd.DataFrame(
        {
            "available_at": available,
            "primary": primary,
            "secondary": secondary,
            "confidence": confidence,
            "direction": direction,
            "range_bps": range_bps,
            "source_event": source_event,
            "below_minimum": below,
            "above_maximum": above,
            "eligible": source_event & ~below & ~above,
        },
        index=bars.index,
    )


def _directions(primary: pd.Series, secondary: pd.Series) -> pd.Series:
    direction = pd.Series(pd.NA, index=primary.index, dtype="object")
    direction.loc[primary.eq("TREND_DOWN")] = "short"
    direction.loc[primary.eq("TREND_UP")] = "long"
    upward = primary.eq("BREAKOUT") & secondary.eq("BK_UPWARD")
    direction.loc[upward] = "long"
    return direction


def _range_bps(bars: pd.DataFrame) -> pd.Series:
    opening = pd.to_numeric(bars["open"], errors="raise")
    high = pd.to_numeric(bars["high"], errors="raise")
    low = pd.to_numeric(bars["low"], errors="raise")
    if opening.le(0.0).any() or high.lt(low).any():
        raise ValueError("five-minute bars contain invalid prices")
    values = 10_000.0 * (high - low) / opening
    if not values.map(math.isfinite).all():
        raise ValueError("five-minute range contains a non-finite value")
    return values


def _validated_windows(values: tuple[int, ...]) -> tuple[int, ...]:
    if not values:
        raise ValueError("trailing windows must not be empty")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("trailing windows must be integer days")
    if any(value <= 0 for value in values):
        raise ValueError("trailing windows must be positive")
    if len(values) != len(set(values)):
        raise ValueError("trailing windows must be unique")
    return tuple(sorted(values))


def _validate_frame(frame: pd.DataFrame, label: str) -> None:
    if frame.empty:
        raise ValueError(f"{label} must not be empty")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{label} require a timezone-aware DatetimeIndex")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError(f"{label} timestamps must be ordered and unique")


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {missing}")


def _excluded(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].sum())


def _counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    values = frame[column].astype(str).value_counts().sort_index()
    return {str(name): int(count) for name, count in values.items()}


def _trailing(
    events: pd.DataFrame,
    end: pd.Timestamp,
    windows: tuple[int, ...],
) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    for days in windows:
        selected = events.loc[events.index >= end - pd.Timedelta(days=days)]
        report[str(days)] = {
            "events": len(selected),
            "long": int(selected["direction"].eq("long").sum()),
            "short": int(selected["direction"].eq("short").sum()),
        }
    return report


def _gap_summary(events: pd.DataFrame) -> dict[str, float | int | None]:
    gaps = events["available_at"].diff().dropna().dt.total_seconds() / 3_600.0
    if gaps.empty:
        return _empty_gap_summary()
    return {
        "minimum": float(gaps.min()),
        "median": float(gaps.median()),
        "p75": float(gaps.quantile(0.75)),
        "p90": float(gaps.quantile(0.90)),
        "maximum": float(gaps.max()),
        "greater_than_24h": int(gaps.gt(24.0).sum()),
        "greater_than_72h": int(gaps.gt(72.0).sum()),
    }


def _empty_gap_summary() -> dict[str, float | int | None]:
    return {
        "minimum": None,
        "median": None,
        "p75": None,
        "p90": None,
        "maximum": None,
        "greater_than_24h": 0,
        "greater_than_72h": 0,
    }


def _event_rows(events: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {
            "label_time_utc": stamp.isoformat(),
            "available_at_utc": row["available_at"].isoformat(),
            "direction": str(row["direction"]),
            "primary": str(row["primary"]),
            "secondary": str(row["secondary"]) or None,
            "confidence": float(row["confidence"]),
            "range_bps": float(row["range_bps"]),
        }
        for stamp, row in events.iterrows()
    ]


def _limitations() -> list[str]:
    return [
        "Signal frequency does not measure fills, returns, or profitability.",
        "The first label is not treated as an onset because prior state is unknown.",
        "Continuity-filled bars retain explicit hl_gap_fill provenance.",
        "Historical cadence does not guarantee the next live event time.",
    ]
