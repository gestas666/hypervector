"""Conservative directional triple-barrier labels on five-minute bars."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

import math
import pandas as pd


Direction = Literal["long", "short"]
BarrierStatus = Literal[
    "target",
    "stop",
    "ambiguous_stop_first",
    "timeout",
    "truncated",
]
_BAR_DURATION = timedelta(minutes=5)


@dataclass(frozen=True)
class DirectionalBarrierSpec:
    """Frozen favorable, adverse, and maximum-hold label boundaries."""

    target_bps: float = 25.0
    stop_bps: float = 18.0
    horizon_bars: int = 12

    def __post_init__(self) -> None:
        values = (self.target_bps, self.stop_bps)
        if not all(math.isfinite(value) and value > 0.0 for value in values):
            raise ValueError("barrier distances must be finite and positive")
        if self.horizon_bars != 12:
            raise ValueError("low-timeframe barrier horizon must equal 12 bars")


@dataclass(frozen=True)
class DirectionalBarrierOutcome:
    """One side-specific result with causal entry and resolution timestamps."""

    signal_time_utc: datetime
    entry_time_utc: datetime | None
    outcome_time_utc: datetime
    side: Direction
    status: BarrierStatus
    entry_price: float | None
    exit_price: float | None
    gross_return_bps: float | None
    ambiguous: bool


def label_directional_barriers(
    bars: pd.DataFrame,
    signal_times: pd.DatetimeIndex,
    spec: DirectionalBarrierSpec,
) -> pd.DataFrame:
    """Label long and short outcomes without optimistic same-bar ordering."""
    times = _validated_bar_times(bars)
    _validate_signals(signal_times, times)
    positions = {stamp: index for index, stamp in enumerate(times)}
    outcomes: list[DirectionalBarrierOutcome] = []
    for signal in signal_times:
        signal_stamp = pd.Timestamp(signal)
        position = positions[signal_stamp]
        for side in ("long", "short"):
            outcomes.append(_label_one(bars, times, position, side, spec))
    return pd.DataFrame([asdict(outcome) for outcome in outcomes])


def _validated_bar_times(bars: pd.DataFrame) -> pd.DatetimeIndex:
    required = {"bar_open_at", "open", "high", "low", "close"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"barrier bars missing columns: {missing}")
    if bars.empty:
        raise ValueError("barrier bars must be non-empty")
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if times.tz is None:
        raise ValueError("barrier bar timestamps must be timezone-aware")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("barrier bars must be ordered and unique")
    return times


def _validate_signals(
    signal_times: pd.DatetimeIndex,
    bar_times: pd.DatetimeIndex,
) -> None:
    if signal_times.empty or signal_times.tz is None:
        raise ValueError("signal timestamps must be non-empty and timezone-aware")
    if not signal_times.is_monotonic_increasing or signal_times.has_duplicates:
        raise ValueError("signal timestamps must be ordered and unique")
    unknown = signal_times.difference(bar_times)
    if not unknown.empty:
        raise ValueError(f"unknown signal timestamp: {unknown[0].isoformat()}")


def _label_one(
    bars: pd.DataFrame,
    times: pd.DatetimeIndex,
    signal_position: int,
    side: Direction,
    spec: DirectionalBarrierSpec,
) -> DirectionalBarrierOutcome:
    signal = _datetime(times[signal_position])
    entry_position = signal_position + 1
    expected_entry = signal + _BAR_DURATION
    if (
        entry_position >= len(bars)
        or _datetime(times[entry_position]) != expected_entry
    ):
        return _truncated(signal, side, signal + _BAR_DURATION)
    entry = _price(bars.iloc[entry_position], "open")
    target, stop = _levels(entry, side, spec)
    end = min(entry_position + spec.horizon_bars, len(bars))
    for position in range(entry_position, end):
        row = bars.iloc[position]
        target_hit, stop_hit = _touches(row, side, target, stop)
        resolved_at = _datetime(times[position]) + _BAR_DURATION
        if target_hit and stop_hit:
            return _resolved(
                signal,
                expected_entry,
                resolved_at,
                side,
                entry,
                stop,
                "ambiguous_stop_first",
                True,
            )
        if stop_hit:
            return _resolved(
                signal, expected_entry, resolved_at, side, entry, stop, "stop", False
            )
        if target_hit:
            return _resolved(
                signal,
                expected_entry,
                resolved_at,
                side,
                entry,
                target,
                "target",
                False,
            )
    if end - entry_position < spec.horizon_bars:
        return _truncated(
            signal,
            side,
            _datetime(times[end - 1]) + _BAR_DURATION,
            expected_entry,
            entry,
        )
    exit_price = _price(bars.iloc[end - 1], "close")
    resolved_at = _datetime(times[end - 1]) + _BAR_DURATION
    return _resolved(
        signal, expected_entry, resolved_at, side, entry, exit_price, "timeout", False
    )


def _levels(
    entry: float,
    side: Direction,
    spec: DirectionalBarrierSpec,
) -> tuple[float, float]:
    sign = 1.0 if side == "long" else -1.0
    target = entry * (1.0 + sign * spec.target_bps / 10_000.0)
    stop = entry * (1.0 - sign * spec.stop_bps / 10_000.0)
    return target, stop


def _touches(
    row: pd.Series,
    side: Direction,
    target: float,
    stop: float,
) -> tuple[bool, bool]:
    high = _price(row, "high")
    low = _price(row, "low")
    if side == "long":
        return high >= target, low <= stop
    return low <= target, high >= stop


def _resolved(
    signal: datetime,
    entry_time: datetime,
    outcome_time: datetime,
    side: Direction,
    entry: float,
    exit_price: float,
    status: BarrierStatus,
    ambiguous: bool,
) -> DirectionalBarrierOutcome:
    sign = 1.0 if side == "long" else -1.0
    gross = round(sign * (exit_price / entry - 1.0) * 10_000.0, 10)
    return DirectionalBarrierOutcome(
        signal,
        entry_time,
        outcome_time,
        side,
        status,
        entry,
        exit_price,
        gross,
        ambiguous,
    )


def _truncated(
    signal: datetime,
    side: Direction,
    outcome_time: datetime,
    entry_time: datetime | None = None,
    entry_price: float | None = None,
) -> DirectionalBarrierOutcome:
    return DirectionalBarrierOutcome(
        signal,
        entry_time,
        outcome_time,
        side,
        "truncated",
        entry_price,
        None,
        None,
        False,
    )


def _price(row: pd.Series, key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"barrier {key} must be finite and positive")
    return value


def _datetime(value: pd.Timestamp) -> datetime:
    return value.to_pydatetime()
