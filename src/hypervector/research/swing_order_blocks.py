"""Causal order-block state reconstructed from the reference Pine indicator."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

_REQUIRED_COLUMNS = ("open", "high", "low", "close")


def build_order_block_state(
    bars: pd.DataFrame,
    *,
    periods: int,
    minimum_move_pct: float,
    use_wicks: bool = False,
) -> pd.DataFrame:
    """Return block detections and active zones only when causally available."""
    frame = _validated_bars(bars)
    _validate_parameters(periods, minimum_move_pct)
    records = _state_records(
        frame, periods=periods, threshold=minimum_move_pct, use_wicks=use_wicks
    )
    return pd.DataFrame.from_records(records, index=frame.index)


def _state_records(
    bars: pd.DataFrame,
    *,
    periods: int,
    threshold: float,
    use_wicks: bool,
) -> list[dict[str, float | bool | int]]:
    values = _bar_arrays(bars)
    green_prefix = _prefix(values["close"] > values["open"])
    red_prefix = _prefix(values["close"] < values["open"])
    state = _empty_state()
    records: list[dict[str, float | bool | int]] = []
    for position in range(len(bars)):
        bull, bear, source = _detections(
            values, green_prefix, red_prefix, position, periods, threshold
        )
        if bull:
            _set_bull(state, values, source, position, use_wicks)
        if bear:
            _set_bear(state, values, source, position, use_wicks)
        _invalidate(state, float(values["close"][position]))
        records.append(_record(state, bull, bear))
    return records


def _detections(
    values: dict[str, np.ndarray],
    green_prefix: np.ndarray,
    red_prefix: np.ndarray,
    position: int,
    periods: int,
    threshold: float,
) -> tuple[bool, bool, int]:
    source = position - periods - 1
    if source < 0:
        return False, False, source
    source_open = float(values["open"][source])
    source_close = float(values["close"][source])
    last_close = float(values["close"][position - 1])
    move = abs(source_close - last_close) / source_close * 100.0
    relevant = move >= threshold
    start = source + 1
    all_green = green_prefix[position] - green_prefix[start] == periods
    all_red = red_prefix[position] - red_prefix[start] == periods
    return (
        relevant and source_close < source_open and all_green,
        relevant and source_close > source_open and all_red,
        source,
    )


def _empty_state() -> dict[str, float | int]:
    return {
        "bull_low": math.nan,
        "bull_high": math.nan,
        "bull_source": math.nan,
        "bull_detected": -1,
        "bear_low": math.nan,
        "bear_high": math.nan,
        "bear_source": math.nan,
        "bear_detected": -1,
    }


def _set_bull(
    state: dict[str, float | int],
    values: dict[str, np.ndarray],
    source: int,
    detected: int,
    use_wicks: bool,
) -> None:
    state["bull_low"] = float(values["low"][source])
    state["bull_high"] = float(values["high" if use_wicks else "open"][source])
    state["bull_source"] = source
    state["bull_detected"] = detected


def _set_bear(
    state: dict[str, float | int],
    values: dict[str, np.ndarray],
    source: int,
    detected: int,
    use_wicks: bool,
) -> None:
    state["bear_high"] = float(values["high"][source])
    state["bear_low"] = float(values["low" if use_wicks else "open"][source])
    state["bear_source"] = source
    state["bear_detected"] = detected


def _invalidate(state: dict[str, float | int], close: float) -> None:
    if math.isfinite(float(state["bull_low"])) and close < state["bull_low"]:
        _clear_side(state, "bull")
    if math.isfinite(float(state["bear_high"])) and close > state["bear_high"]:
        _clear_side(state, "bear")


def _clear_side(state: dict[str, float | int], side: str) -> None:
    state[f"{side}_low"] = math.nan
    state[f"{side}_high"] = math.nan
    state[f"{side}_source"] = math.nan
    state[f"{side}_detected"] = -1


def _record(
    state: dict[str, float | int], bull: bool, bear: bool
) -> dict[str, float | bool | int]:
    direction = _active_direction(state)
    return {
        "bull_ob_detected": bull,
        "bear_ob_detected": bear,
        "active_bull_ob_low": float(state["bull_low"]),
        "active_bull_ob_high": float(state["bull_high"]),
        "active_bear_ob_low": float(state["bear_low"]),
        "active_bear_ob_high": float(state["bear_high"]),
        "bull_ob_source_position": float(state["bull_source"]),
        "bear_ob_source_position": float(state["bear_source"]),
        "active_ob_direction": direction,
    }


def _active_direction(state: dict[str, float | int]) -> int:
    bull_position = int(state["bull_detected"])
    bear_position = int(state["bear_detected"])
    if bull_position < 0 and bear_position < 0:
        return 0
    return 1 if bull_position > bear_position else -1


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_REQUIRED_COLUMNS).difference(bars.columns))
    if missing:
        raise ValueError(f"order-block bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("order-block bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("order-block bars require ordered unique rows")
    values = bars.loc[:, list(_REQUIRED_COLUMNS)].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("order-block OHLC must be finite positive values")
    return bars


def _validate_parameters(periods: int, threshold: float) -> None:
    if isinstance(periods, bool) or not isinstance(periods, int) or periods < 1:
        raise ValueError("order-block periods must be a positive integer")
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("order-block minimum move must be finite and non-negative")


def _bar_arrays(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        column: bars[column].to_numpy(dtype=np.float64) for column in _REQUIRED_COLUMNS
    }


def _prefix(values: np.ndarray) -> np.ndarray:
    return np.concatenate(([0], np.cumsum(values, dtype=np.int64)))
