"""Causal backend decision projection for maker replay."""

from __future__ import annotations

from collections.abc import Sequence
import math

import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    ReplayState,
)

DecisionProjection = tuple[
    Sequence[object],
    Sequence[object],
    Sequence[object],
    Sequence[object],
    Sequence[object],
    Sequence[object],
    Sequence[object],
    pd.DatetimeIndex,
]


def _direction_rows(decisions: pd.DataFrame) -> pd.Series:
    if "entry_direction" in decisions:
        values = decisions["entry_direction"].astype(object)
        return values.where(values.isin(("long", "short")), None)
    required = {"primary_regime", "breakout_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"maker replay decisions missing columns: {sorted(missing)}")
    primary = decisions["primary_regime"].astype(str)
    breakout = decisions["breakout_direction"].astype(object)
    result = pd.Series(None, index=decisions.index, dtype=object)
    result = result.mask(primary.eq(PrimaryRegime.TREND_UP.value), "long")
    result = result.mask(primary.eq(PrimaryRegime.TREND_DOWN.value), "short")
    result = result.mask(
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.UPWARD.value),
        "long",
    )
    return result.mask(
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.DOWNWARD.value),
        "short",
    )


def available_directions(decisions: pd.DataFrame) -> pd.Series:
    """Return entry directions when each completed bar becomes observable."""
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("maker replay decisions require a DatetimeIndex")
    directions = _direction_rows(decisions)
    directions.index = directions.index + pd.Timedelta(minutes=1)
    return directions


def available_structural_directions(decisions: pd.DataFrame) -> pd.Series:
    """Return structural directions used for cancellation and rearm behavior."""
    if "structural_direction" in decisions:
        structural = decisions["structural_direction"].astype(object)
        structural = structural.where(structural.isin(("long", "short")), None)
    else:
        structural = _direction_rows(decisions)
    structural.index = structural.index + pd.Timedelta(minutes=1)
    return structural


def available_reentry_events(decisions: pd.DataFrame) -> pd.Series:
    """Return causal 1m pullback-transition pulses in the 5m direction."""
    required = {"state_1m", "structural_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"re-entry events missing columns: {sorted(missing)}")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("re-entry events require a DatetimeIndex")
    state = decisions["state_1m"].astype(object)
    structural = decisions["structural_direction"].astype(object)
    changed = state.ne(state.shift()) & state.shift().notna()
    long_pullback = structural.eq("long") & state.ne(PrimaryRegime.TREND_UP.value)
    short_pullback = structural.eq("short") & state.ne(PrimaryRegime.TREND_DOWN.value)
    events = pd.Series([None] * len(decisions), index=decisions.index, dtype=object)
    events.loc[changed & long_pullback] = "long"
    events.loc[changed & short_pullback] = "short"
    events.index = events.index + pd.Timedelta(minutes=1)
    return events


def available_maximum_holds(decisions: pd.DataFrame) -> pd.Series:
    """Return optional per-signal holding deadlines when each bar is observable."""
    values = decisions.get(
        "maximum_hold_seconds",
        pd.Series(None, index=decisions.index, dtype=object),
    )
    numeric = pd.to_numeric(values, errors="raise")
    invalid = numeric.notna() & numeric.map(
        lambda value: not math.isfinite(float(value)) or float(value) <= 0.0
    )
    if invalid.any():
        raise ValueError("decision maximum_hold_seconds must be finite and positive")
    result = numeric.astype(object).where(numeric.notna(), None)
    result.index = result.index + pd.Timedelta(minutes=1)
    return result


def available_entry_allocation_multipliers(decisions: pd.DataFrame) -> pd.Series:
    """Return causal per-entry allocation multipliers for research sizing."""
    values = decisions.get(
        "entry_allocation_multiplier",
        pd.Series(1.0, index=decisions.index, dtype=float),
    )
    numeric = pd.to_numeric(values, errors="raise")
    invalid = numeric.isna() | ~numeric.map(
        lambda value: math.isfinite(float(value)) and 0.0 < float(value) <= 1.0
    )
    if invalid.any():
        raise ValueError("decision entry_allocation_multiplier must be within (0, 1]")
    result = numeric.astype(float)
    result.index = result.index + pd.Timedelta(minutes=1)
    return result


def available_entry_stops(decisions: pd.DataFrame) -> pd.Series:
    """Return optional structural stop levels when each bar becomes observable."""
    values = decisions.get(
        "entry_stop_price",
        pd.Series(None, index=decisions.index, dtype=object),
    )
    numeric = pd.to_numeric(values, errors="raise")
    invalid = numeric.notna() & numeric.map(
        lambda value: not math.isfinite(float(value)) or float(value) <= 0.0
    )
    if invalid.any():
        raise ValueError("decision entry_stop_price must be finite and positive")
    result = numeric.astype(object).where(numeric.notna(), None)
    result.index = result.index + pd.Timedelta(minutes=1)
    return result


def available_entry_stop_margin_pcts(decisions: pd.DataFrame) -> pd.Series:
    """Return optional per-entry margin stops when each bar becomes observable."""
    values = decisions.get(
        "entry_stop_margin_pct",
        pd.Series(None, index=decisions.index, dtype=object),
    )
    numeric = pd.to_numeric(values, errors="raise")
    invalid = numeric.notna() & numeric.map(
        lambda value: not math.isfinite(float(value)) or not 0.0 < float(value) < 100.0
    )
    if invalid.any():
        raise ValueError("decision entry_stop_margin_pct must be within (0, 100)")
    result = numeric.astype(object).where(numeric.notna(), None)
    result.index = result.index + pd.Timedelta(minutes=1)
    return result


def market_at(
    position: int,
    values: Sequence[object],
    structural_values: Sequence[object],
    index: pd.DatetimeIndex,
) -> tuple[Direction | None, Direction | None, pd.Timestamp | None]:
    """Project the latest causally available entry and structural directions."""
    if position < 0:
        return None, None, None
    value = values[position]
    structural_value = structural_values[position]
    desired = value if value in ("long", "short") else None
    structural = structural_value if structural_value in ("long", "short") else None
    return desired, structural, pd.Timestamp(index[position])


def reentry_event_at(
    position: int,
    values: Sequence[object],
) -> Direction | None:
    """Return the latest causal pullback-transition pulse, if present."""
    if position < 0:
        return None
    value = values[position]
    return value if value in ("long", "short") else None


def maximum_hold_at(position: int, values: Sequence[object]) -> float | None:
    """Return the latest causally available per-signal holding deadline."""
    if position < 0:
        return None
    value = values[position]
    return None if value is None or pd.isna(value) else float(value)


def projected_market_at(
    position: int,
    projection: DecisionProjection,
) -> tuple[
    Direction | None,
    Direction | None,
    pd.Timestamp | None,
    Direction | None,
    float | None,
    float | None,
    float | None,
    float,
]:
    """Project all causal decision metadata used by one tape event."""
    (
        directions,
        structural,
        reentries,
        maximum_holds,
        stops,
        stop_margin_pcts,
        allocation_multipliers,
        index,
    ) = projection
    desired, structure, signal_time = market_at(position, directions, structural, index)
    return (
        desired,
        structure,
        signal_time,
        reentry_event_at(position, reentries),
        maximum_hold_at(position, maximum_holds),
        maximum_hold_at(position, stops),
        maximum_hold_at(position, stop_margin_pcts),
        float(allocation_multipliers[position]) if position >= 0 else 1.0,
    )


def decision_projection(
    directions: pd.Series,
    structural_directions: pd.Series,
    reentry_events: pd.Series,
    maximum_holds: pd.Series,
    entry_stops: pd.Series,
    entry_stop_margin_pcts: pd.Series,
    allocation_multipliers: pd.Series,
) -> DecisionProjection:
    """Validate and materialize aligned causal decision streams."""
    if not isinstance(directions.index, pd.DatetimeIndex):
        raise ValueError("maker replay directions require a DatetimeIndex")
    if not directions.index.equals(structural_directions.index):
        raise ValueError("entry and structural directions require the same index")
    if not directions.index.equals(reentry_events.index):
        raise ValueError("entry directions and re-entry events require the same index")
    if not directions.index.equals(maximum_holds.index):
        raise ValueError("entry directions and maximum holds require the same index")
    if not directions.index.equals(entry_stops.index):
        raise ValueError("entry directions and stop prices require the same index")
    if not directions.index.equals(entry_stop_margin_pcts.index):
        raise ValueError("entry directions and margin stops require the same index")
    if not directions.index.equals(allocation_multipliers.index):
        raise ValueError(
            "entry directions and allocation multipliers require the same index"
        )
    return (
        directions.to_numpy(dtype=object),
        structural_directions.to_numpy(dtype=object),
        reentry_events.to_numpy(dtype=object),
        maximum_holds.to_numpy(dtype=object),
        entry_stops.to_numpy(dtype=object),
        entry_stop_margin_pcts.to_numpy(dtype=object),
        allocation_multipliers.to_numpy(dtype=object),
        directions.index,
    )


def consume_liquidation_cooldown_signal(
    state: ReplayState,
    desired: Direction,
    signal_time: pd.Timestamp | None,
    timestamp: pd.Timestamp,
    config: MakerReplayConfig,
) -> bool:
    """Consume a fresh same-side signal during a post-liquidation cooldown."""
    if signal_time is None or signal_time == state.last_signal:
        return False
    if state.last_exit_time is None or signal_time <= state.last_exit_time:
        return False
    if not state.trades:
        return False
    last_trade = state.trades[-1]
    if last_trade.status != "liquidated" or last_trade.direction != desired:
        return False
    elapsed = (timestamp - state.last_exit_time).total_seconds()
    if elapsed >= config.liquidation_reentry_cooldown_seconds:
        return False
    state.last_signal = signal_time
    return True
