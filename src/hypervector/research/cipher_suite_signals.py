"""Causal directional states for exact-source Cipher suite research."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from numpy.typing import NDArray


CIPHER_VARIANTS: tuple[str, ...] = (
    "cipher_a",
    "cipher_b",
    "cipher_dbsi",
    "cipher_a_b_any",
    "cipher_a_b_all",
    "cipher_suite_2of3",
    "cipher_suite_3of3",
)
CIPHER_BUNDLE_VARIANTS: tuple[str, ...] = (
    "cipher_a_b_trigger",
    "cipher_a_b_dbsi_trigger",
    "cipher_a_b_cross",
    "cipher_a_b_flow_cross",
)
ALL_CIPHER_VARIANTS: tuple[str, ...] = CIPHER_VARIANTS + CIPHER_BUNDLE_VARIANTS


def state_from_events(
    long_events: NDArray[np.bool_],
    short_events: NDArray[np.bool_],
) -> NDArray[np.int8]:
    """Persist the last unambiguous directional event as -1, 0, or +1."""
    long_values = np.asarray(long_events, dtype=np.bool_)
    short_values = np.asarray(short_events, dtype=np.bool_)
    if long_values.ndim != 1 or long_values.shape != short_values.shape:
        raise ValueError("Cipher event arrays must be one-dimensional and aligned")
    output = np.zeros(len(long_values), dtype=np.int8)
    state = np.int8(0)
    for index, (long_event, short_event) in enumerate(
        zip(long_values, short_values, strict=True)
    ):
        if long_event != short_event:
            state = np.int8(1 if long_event else -1)
        output[index] = state
    return output


def cipher_b_states_from_waves(
    wt1: NDArray[np.float64],
    wt2: NDArray[np.float64],
    *,
    overbought: float = 53.0,
    oversold: float = -53.0,
) -> NDArray[np.int8]:
    """Apply Cipher B Pine cross direction and WT2 extreme thresholds."""
    first = np.asarray(wt1, dtype=np.float64)
    second = np.asarray(wt2, dtype=np.float64)
    if first.ndim != 1 or first.shape != second.shape:
        raise ValueError("WaveTrend arrays must be one-dimensional and aligned")
    events = cipher_b_events_from_waves(
        first, second, overbought=overbought, oversold=oversold
    )
    return state_from_events(events == 1, events == -1)


def cipher_b_events_from_waves(
    wt1: NDArray[np.float64],
    wt2: NDArray[np.float64],
    *,
    overbought: float = 53.0,
    oversold: float = -53.0,
) -> NDArray[np.int8]:
    """Return +1/-1 only on exact Cipher B Pine buy/sell trigger bars."""
    first = np.asarray(wt1, dtype=np.float64)
    second = np.asarray(wt2, dtype=np.float64)
    if first.ndim != 1 or first.shape != second.shape:
        raise ValueError("WaveTrend arrays must be one-dimensional and aligned")
    crosses = cipher_b_cross_events_from_waves(first, second)
    return np.where(
        (crosses == 1) & (second <= oversold),
        1,
        np.where((crosses == -1) & (second >= overbought), -1, 0),
    ).astype(np.int8)


def cipher_b_cross_events_from_waves(
    wt1: NDArray[np.float64],
    wt2: NDArray[np.float64],
) -> NDArray[np.int8]:
    """Return Pine's small-dot event, equivalent to WT VWAP crossing zero."""
    first = np.asarray(wt1, dtype=np.float64)
    second = np.asarray(wt2, dtype=np.float64)
    if first.ndim != 1 or first.shape != second.shape:
        raise ValueError("WaveTrend arrays must be one-dimensional and aligned")
    valid = np.isfinite(first) & np.isfinite(second)
    cross_up = np.zeros(len(first), dtype=np.bool_)
    cross_down = np.zeros(len(first), dtype=np.bool_)
    cross_up[1:] = (
        valid[:-1] & valid[1:] & (first[:-1] <= second[:-1]) & (first[1:] > second[1:])
    )
    cross_down[1:] = (
        valid[:-1] & valid[1:] & (first[:-1] >= second[:-1]) & (first[1:] < second[1:])
    )
    return np.where(cross_up, 1, np.where(cross_down, -1, 0)).astype(np.int8)


def pine_mfi_source(
    source: NDArray[np.float64],
    volume: NDArray[np.float64],
    *,
    period: int,
) -> NDArray[np.float64]:
    """Compute Pine ``ta.mfi(source, period)`` using the supplied source."""
    values = np.asarray(source, dtype=np.float64)
    volumes = np.asarray(volume, dtype=np.float64)
    if values.ndim != 1 or values.shape != volumes.shape:
        raise ValueError("MFI source and volume must be one-dimensional and aligned")
    if period < 1:
        raise ValueError("MFI period must be positive")
    positive = np.zeros(len(values), dtype=np.float64)
    negative = np.zeros(len(values), dtype=np.float64)
    changes = np.diff(values)
    positive[1:] = np.where(changes > 0.0, values[1:] * volumes[1:], 0.0)
    negative[1:] = np.where(changes < 0.0, values[1:] * volumes[1:], 0.0)
    positive_sum = pd.Series(positive).rolling(period).sum().to_numpy()
    negative_sum = pd.Series(negative).rolling(period).sum().to_numpy()
    output = np.full(len(values), np.nan, dtype=np.float64)
    ready = np.arange(len(values)) >= period
    both_zero = ready & (positive_sum == 0.0) & (negative_sum == 0.0)
    output[ready & (negative_sum == 0.0) & ~both_zero] = 100.0
    output[ready & (positive_sum == 0.0) & (negative_sum > 0.0)] = 0.0
    normal = ready & (positive_sum > 0.0) & (negative_sum > 0.0)
    output[normal] = (
        100.0 * positive_sum[normal] / (positive_sum[normal] + negative_sum[normal])
    )
    return output


def pine_aroon_bullish(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    *,
    period: int,
) -> NDArray[np.bool_]:
    """Return DBSI's exact manual Pine Aroon bullish condition."""
    highs = np.asarray(high, dtype=np.float64)
    lows = np.asarray(low, dtype=np.float64)
    if highs.ndim != 1 or highs.shape != lows.shape:
        raise ValueError("Aroon high and low must be one-dimensional and aligned")
    if period < 1:
        raise ValueError("Aroon period must be positive")
    output = np.zeros(len(highs), dtype=np.bool_)
    for index in range(period - 1, len(highs)):
        high_window = highs[index - period + 1 : index + 1]
        low_window = lows[index - period + 1 : index + 1]
        high_offset = period - 1 - _last_extreme_index(high_window, max)
        low_offset = period - 1 - _last_extreme_index(low_window, min)
        output[index] = high_offset < low_offset
    return output


def compose_cipher_entries(states: pd.DataFrame) -> pd.DataFrame:
    """Compose component states and emit only causal directional onsets."""
    _validate_states(states)
    rules = (
        ("cipher_a", ("cipher_a",), 1),
        ("cipher_b", ("cipher_b",), 1),
        ("cipher_dbsi", ("cipher_dbsi",), 1),
        ("cipher_a_b_any", ("cipher_a", "cipher_b"), 1),
        ("cipher_a_b_all", ("cipher_a", "cipher_b"), 2),
        ("cipher_suite_2of3", tuple(states.columns), 2),
        ("cipher_suite_3of3", tuple(states.columns), 3),
    )
    rows: list[dict[str, object]] = []
    for candidate, components, threshold in rules:
        _append_transitions(rows, states, candidate, components, threshold)
    return pd.DataFrame(rows, columns=["candidate", "signal_time_utc", "side"])


def compose_cipher_bundle_entries(components: pd.DataFrame) -> pd.DataFrame:
    """Use A for trend, B for timing, and DBSI as strict optional confirmation."""
    expected = {
        "cipher_a_trend",
        "cipher_b_trigger",
        "cipher_b_cross_trigger",
        "cipher_b_money_flow",
        "cipher_dbsi",
    }
    if set(components.columns) != expected:
        raise ValueError("Cipher bundle requires A trend, B trigger, and DBSI")
    _validate_component_frame(components)
    a_trend = components["cipher_a_trend"]
    b_trigger = components["cipher_b_trigger"]
    b_cross = components["cipher_b_cross_trigger"]
    money_flow = components["cipher_b_money_flow"]
    dbsi = components["cipher_dbsi"]
    rows: list[dict[str, object]] = []
    for side, direction in (("long", 1), ("short", -1)):
        aligned = b_trigger.eq(direction) & a_trend.eq(direction)
        _append_bundle_rows(rows, components.index[aligned], "cipher_a_b_trigger", side)
        strict = aligned & dbsi.eq(direction)
        _append_bundle_rows(
            rows, components.index[strict], "cipher_a_b_dbsi_trigger", side
        )
        cross = b_cross.eq(direction) & a_trend.eq(direction)
        _append_bundle_rows(rows, components.index[cross], "cipher_a_b_cross", side)
        flow_cross = cross & money_flow.eq(direction)
        _append_bundle_rows(
            rows, components.index[flow_cross], "cipher_a_b_flow_cross", side
        )
    return pd.DataFrame(rows, columns=["candidate", "signal_time_utc", "side"])


def _last_extreme_index(values: NDArray[np.float64], function: object) -> int:
    extreme = function(values)
    return int(np.flatnonzero(values == extreme)[-1])


def _validate_states(states: pd.DataFrame) -> None:
    expected = {"cipher_a", "cipher_b", "cipher_dbsi"}
    if set(states.columns) != expected:
        raise ValueError("Cipher states must contain exactly A, B, and DBSI")
    if not isinstance(states.index, pd.DatetimeIndex) or states.index.tz is None:
        raise ValueError("Cipher states require a timezone-aware DatetimeIndex")
    if (
        states.empty
        or not states.index.is_monotonic_increasing
        or states.index.has_duplicates
    ):
        raise ValueError("Cipher states must be non-empty, ordered, and unique")
    values = states.to_numpy(dtype=np.int8)
    if not np.isin(values, (-1, 0, 1)).all():
        raise ValueError("Cipher component states must be -1, 0, or +1")


def _validate_component_frame(components: pd.DataFrame) -> None:
    if (
        not isinstance(components.index, pd.DatetimeIndex)
        or components.index.tz is None
    ):
        raise ValueError("Cipher bundle requires a timezone-aware DatetimeIndex")
    if components.empty or components.index.has_duplicates:
        raise ValueError("Cipher bundle components must be non-empty and unique")
    if not components.index.is_monotonic_increasing:
        raise ValueError("Cipher bundle components must be chronological")
    if not np.isin(components.to_numpy(dtype=np.int8), (-1, 0, 1)).all():
        raise ValueError("Cipher bundle values must be -1, 0, or +1")


def _append_bundle_rows(
    rows: list[dict[str, object]],
    timestamps: pd.DatetimeIndex,
    candidate: str,
    side: str,
) -> None:
    for timestamp in timestamps:
        rows.append(
            {"candidate": candidate, "signal_time_utc": timestamp, "side": side}
        )


def _append_transitions(
    rows: list[dict[str, object]],
    states: pd.DataFrame,
    candidate: str,
    components: Iterable[str],
    threshold: int,
) -> None:
    selected = states.loc[:, list(components)]
    long_count = selected.eq(1).sum(axis=1)
    short_count = selected.eq(-1).sum(axis=1)
    long_state = long_count.ge(threshold) & short_count.lt(threshold)
    short_state = short_count.ge(threshold) & long_count.lt(threshold)
    long_entry = long_state & ~long_state.shift(1, fill_value=False)
    short_entry = short_state & ~short_state.shift(1, fill_value=False)
    for timestamp in states.index[long_entry]:
        rows.append(
            {"candidate": candidate, "signal_time_utc": timestamp, "side": "long"}
        )
    for timestamp in states.index[short_entry]:
        rows.append(
            {"candidate": candidate, "signal_time_utc": timestamp, "side": "short"}
        )
