"""Causal SuperTrend TP Dimensions with explicit sample support."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.pine_stack_native_bars import validated_native_bars
from hypervector.research.pine_stack_sentiment_indicators import classic_supertrend

_AxisPoint = tuple[float, float, float]


@dataclass(frozen=True)
class TpDimensionsConfig:
    """Source parameters plus minimum support for executable exit challengers."""

    atr_period: int = 10
    supertrend_factor: float = 3.0
    pivot_width: int = 3
    bin_count: int = 5
    relative_volume_lookback: int = 50
    range_lookback: int = 20
    maximum_history: int = 2_000
    include_time_of_day: bool = True
    minimum_directional_pool: int = 25
    minimum_conditional_support: int = 5

    def __post_init__(self) -> None:
        """Reject invalid TP-density lengths, support, and factor settings."""
        integers = (
            self.atr_period,
            self.pivot_width,
            self.bin_count,
            self.relative_volume_lookback,
            self.range_lookback,
            self.maximum_history,
            self.minimum_directional_pool,
            self.minimum_conditional_support,
        )
        if any(isinstance(value, bool) or value < 1 for value in integers):
            raise ValueError("TP Dimensions integer parameters must be positive")
        if self.pivot_width < 2 or self.bin_count < 2:
            raise ValueError("TP Dimensions pivot width and bins must be at least two")
        if not math.isfinite(self.supertrend_factor) or self.supertrend_factor <= 0.0:
            raise ValueError("TP Dimensions SuperTrend factor must be positive")


def build_tp_dimensions(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
    config: TpDimensionsConfig | None = None,
) -> pd.DataFrame:
    """Return causal density-match scores, support, pivots, and exit onsets."""
    cfg = config or TpDimensionsConfig()
    frame = validated_native_bars(bars, bar_minutes=bar_minutes)
    _, direction = classic_supertrend(
        frame["high"],
        frame["low"],
        frame["close"],
        atr_period=cfg.atr_period,
        factor=cfg.supertrend_factor,
    )
    axes = _context_axes(frame, cfg)
    metrics = _sequential_density_metrics(frame, axes, direction, cfg)
    result = pd.concat(
        [
            frame.loc[:, ["bar_open_at"]],
            direction.rename("supertrend_direction"),
            metrics,
        ],
        axis=1,
    )
    result["decision_time_utc"] = result["bar_open_at"] + pd.Timedelta(
        minutes=bar_minutes
    )
    score = result["density_match_score"]
    result["density_80_onset"] = score.ge(80.0) & ~score.shift(1).ge(80.0)
    result["density_100_onset"] = score.ge(99.999) & ~score.shift(1).ge(99.999)
    result["score_semantics"] = "density_match_not_probability"
    result["time_of_day_axis"] = cfg.include_time_of_day
    return result


def _context_axes(frame: pd.DataFrame, config: TpDimensionsConfig) -> pd.DataFrame:
    volume = frame["volume"].astype(float)
    relative = volume.rolling(
        config.relative_volume_lookback,
        min_periods=config.relative_volume_lookback,
    ).apply(lambda values: float(np.mean(values <= values[-1]) * 100.0), raw=True)
    times = pd.DatetimeIndex(frame["bar_open_at"])
    elapsed = (times - times.floor("D")).total_seconds()
    time_of_day = pd.Series(elapsed / 86_400.0 * 100.0, index=frame.index)
    highest = (
        frame["high"]
        .rolling(config.range_lookback, min_periods=config.range_lookback)
        .max()
    )
    lowest = (
        frame["low"]
        .rolling(config.range_lookback, min_periods=config.range_lookback)
        .min()
    )
    range_position = (
        (frame["close"] - lowest) / (highest - lowest).replace(0.0, np.nan) * 100.0
    )
    return pd.DataFrame(
        {
            "relative_volume": relative,
            "time_of_day": time_of_day,
            "range_position": range_position,
        }
    )


def _sequential_density_metrics(
    frame: pd.DataFrame,
    axes: pd.DataFrame,
    direction: pd.Series,
    config: TpDimensionsConfig,
) -> pd.DataFrame:
    rows: list[dict[str, float | bool | int]] = []
    bull_pool: list[_AxisPoint] = []
    bear_pool: list[_AxisPoint] = []
    highs = frame["high"].to_numpy(dtype=np.float64)
    lows = frame["low"].to_numpy(dtype=np.float64)
    states = direction.to_numpy(dtype=np.int8)
    for position in range(len(frame)):
        bull_pivot, bear_pivot = _record_confirmed_pivot(
            position, highs, lows, states, axes, bull_pool, bear_pool, config
        )
        pool = bull_pool if states[position] == 1 else bear_pool
        score = _score_pool(pool, axes.iloc[position], config)
        rows.append(_metric_row(score, len(pool), bull_pivot, bear_pivot, config))
    return pd.DataFrame(rows, index=frame.index)


def _record_confirmed_pivot(
    confirmation: int,
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    direction: NDArray[np.int8],
    axes: pd.DataFrame,
    bull_pool: list[_AxisPoint],
    bear_pool: list[_AxisPoint],
    config: TpDimensionsConfig,
) -> tuple[bool, bool]:
    width = config.pivot_width
    if confirmation < 2 * width:
        return False, False
    center = confirmation - width
    left = slice(center - width, center)
    right = slice(center + 1, center + width + 1)
    high_pivot = high[center] >= high[left].max() and high[center] > high[right].max()
    low_pivot = low[center] <= low[left].min() and low[center] < low[right].min()
    bull = bool(high_pivot and direction[center] == 1)
    bear = bool(low_pivot and direction[center] == -1)
    point = tuple(float(value) for value in axes.iloc[center])
    if bull:
        bull_pool.insert(0, point)
        del bull_pool[config.maximum_history :]
    if bear:
        bear_pool.insert(0, point)
        del bear_pool[config.maximum_history :]
    return bull, bear


def _score_pool(
    pool: list[_AxisPoint],
    current: pd.Series,
    config: TpDimensionsConfig,
) -> tuple[float, tuple[float, float, float], tuple[int, int, int]]:
    enabled = (0, 1, 2) if config.include_time_of_day else (0, 2)
    current_values = tuple(float(value) for value in current)
    current_bins = tuple(_bin(value, config.bin_count) for value in current_values)
    scores = [math.nan, math.nan, math.nan]
    supports = [0, 0, 0]
    for axis in enabled:
        score, support = _conditional_score(
            pool, current_bins, axis, enabled, config.bin_count
        )
        scores[axis], supports[axis] = score, support
    active = [scores[axis] for axis in enabled if math.isfinite(scores[axis])]
    raw = float(np.mean(active)) if active else math.nan
    return raw, tuple(scores), tuple(supports)


def _conditional_score(
    pool: list[_AxisPoint],
    current_bins: tuple[int | None, int | None, int | None],
    axis: int,
    enabled: tuple[int, ...],
    bins: int,
) -> tuple[float, int]:
    if current_bins[axis] is None:
        return math.nan, 0
    values: list[float] = []
    for point in pool:
        point_bins = tuple(_bin(value, bins) for value in point)
        if point_bins[axis] is None:
            continue
        if all(
            point_bins[other] == current_bins[other]
            for other in enabled
            if other != axis
        ):
            values.append(point[axis])
    if not values:
        return math.nan, 0
    counts = np.bincount([int(_bin(value, bins)) for value in values], minlength=bins)
    current_count = counts[int(current_bins[axis])]
    peak = int(counts.max())
    return (100.0 * current_count / peak if peak else math.nan), len(values)


def _metric_row(
    scored: tuple[float, tuple[float, float, float], tuple[int, int, int]],
    pool_size: int,
    bull_pivot: bool,
    bear_pivot: bool,
    config: TpDimensionsConfig,
) -> dict[str, float | bool | int]:
    raw, scores, supports = scored
    enabled_supports = (
        supports if config.include_time_of_day else (supports[0], supports[2])
    )
    minimum_support = min(enabled_supports) if enabled_supports else 0
    eligible = (
        math.isfinite(raw)
        and pool_size >= config.minimum_directional_pool
        and minimum_support >= config.minimum_conditional_support
    )
    return {
        "relative_volume_score": scores[0],
        "time_of_day_score": scores[1],
        "range_position_score": scores[2],
        "directional_pool_size": pool_size,
        "minimum_axis_support": minimum_support,
        "density_match_raw": raw,
        "density_match_score": raw if eligible else math.nan,
        "insufficient_support": math.isfinite(raw) and not eligible,
        "confirmed_bull_pivot": bull_pivot,
        "confirmed_bear_pivot": bear_pivot,
    }


def _bin(value: float, count: int) -> int | None:
    if not math.isfinite(value):
        return None
    return min(count - 1, max(0, int(math.floor(value / (100.0 / count)))))
