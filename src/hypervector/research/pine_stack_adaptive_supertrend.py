"""Causal correction of the CS Scalper adaptive-SuperTrend entry source."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.pine_stack_native_bars import validated_native_bars


@dataclass(frozen=True)
class AdaptiveSupertrendConfig:
    """Bounded adaptive-SuperTrend parameters derived from CS Scalper."""

    atr_period: int = 10
    sensitivity: float = 5.0
    factor_step: float = 0.5
    performance_alpha: float = 10.0
    maximum_cluster_iterations: int = 250

    def __post_init__(self) -> None:
        """Reject parameters outside the source's supported mechanical range."""
        integers = (self.atr_period, self.maximum_cluster_iterations)
        if any(isinstance(value, bool) or value < 1 for value in integers):
            raise ValueError("adaptive-SuperTrend integer parameters must be positive")
        finite = (self.sensitivity, self.factor_step, self.performance_alpha)
        if any(not math.isfinite(value) or value <= 0.0 for value in finite):
            raise ValueError(
                "adaptive-SuperTrend parameters must be positive and finite"
            )
        if not 1.0 <= self.sensitivity <= 26.0:
            raise ValueError("adaptive-SuperTrend sensitivity must be within [1, 26]")

    @property
    def factors(self) -> NDArray[np.float64]:
        """Return the source-derived inclusive candidate factor grid."""
        lower = max(self.sensitivity - 4.0, 1.0)
        upper = min(self.sensitivity, 26.0)
        steps = int(math.floor((upper - lower) / self.factor_step + 1e-12))
        return lower + np.arange(steps + 1, dtype=np.float64) * self.factor_step


@dataclass
class _FactorState:
    upper: float = math.nan
    lower: float = math.nan
    output: float = math.nan
    performance: float = 0.0
    trend: int = -1


@dataclass
class _TargetState:
    upper: float = math.nan
    lower: float = math.nan
    trend: int = -1


def pine_rma(values: NDArray[np.float64], *, length: int) -> NDArray[np.float64]:
    """Return Pine-compatible RMA with an SMA seed and Wilder recurrence."""
    source = np.asarray(values, dtype=np.float64)
    if source.ndim != 1 or isinstance(length, bool) or length < 1:
        raise ValueError("Pine RMA requires one-dimensional values and positive length")
    output = np.full(len(source), np.nan, dtype=np.float64)
    for position in range(length - 1, len(source)):
        window = source[position - length + 1 : position + 1]
        if np.isfinite(window).all():
            output[position] = float(window.mean())
            seed_position = position
            break
    else:
        return output
    alpha = 1.0 / length
    for position in range(seed_position + 1, len(source)):
        if np.isfinite(source[position]):
            output[position] = (
                alpha * source[position] + (1.0 - alpha) * output[position - 1]
            )
    return output


def build_adaptive_supertrend(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
    config: AdaptiveSupertrendConfig | None = None,
) -> pd.DataFrame:
    """Return append-invariant selected factors, trend state, and entry onsets."""
    cfg = config or AdaptiveSupertrendConfig()
    frame = validated_native_bars(bars, bar_minutes=bar_minutes)
    high = frame["high"].to_numpy(dtype=np.float64)
    low = frame["low"].to_numpy(dtype=np.float64)
    close = frame["close"].to_numpy(dtype=np.float64)
    atr = pine_rma(_true_range(high, low, close), length=cfg.atr_period)
    factor_states = [_FactorState() for _ in cfg.factors]
    target = _TargetState()
    selected = np.full(len(frame), np.nan, dtype=np.float64)
    trail = np.full(len(frame), np.nan, dtype=np.float64)
    trends = np.zeros(len(frame), dtype=np.int8)
    for position in range(len(frame)):
        if not math.isfinite(float(atr[position])):
            continue
        _update_factor_states(
            factor_states, cfg.factors, high, low, close, atr, position, cfg
        )
        performances = np.array(
            [state.performance for state in factor_states], dtype=np.float64
        )
        factor = _best_cluster_factor(
            performances, cfg.factors, cfg.maximum_cluster_iterations
        )
        selected[position] = factor
        trail[position], trends[position] = _update_target(
            target, factor, high, low, close, atr, position
        )
    prior = np.concatenate(([0], trends[:-1])).astype(np.int8)
    result = frame.loc[:, ["bar_open_at"]].copy()
    result["decision_time_utc"] = result["bar_open_at"] + pd.Timedelta(
        minutes=bar_minutes
    )
    result["atr"] = atr
    result["selected_factor"] = selected
    result["trailing_stop"] = trail
    result["trend_state"] = trends
    result["long_onset"] = (trends == 1) & (prior != 1)
    result["short_onset"] = (trends == -1) & (prior != -1) & np.isfinite(trail)
    result["source_translation"] = "cs_causal_corrected"
    return result


def _true_range(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.float64]:
    output = high - low
    if len(close) > 1:
        output[1:] = np.maximum.reduce(
            (output[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
        )
    return output


def _update_factor_states(
    states: list[_FactorState],
    factors: NDArray[np.float64],
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    atr: NDArray[np.float64],
    position: int,
    config: AdaptiveSupertrendConfig,
) -> None:
    midpoint = (high[position] + low[position]) / 2.0
    prior_close = close[position - 1] if position else close[position]
    alpha = 2.0 / (config.performance_alpha + 1.0)
    for factor, state in zip(factors, states, strict=True):
        proposed_upper = midpoint + atr[position] * factor
        proposed_lower = midpoint - atr[position] * factor
        if not math.isfinite(state.upper):
            state.upper, state.lower = proposed_upper, proposed_lower
        else:
            prior_upper, prior_lower = state.upper, state.lower
            state.trend = (
                1
                if close[position] > prior_upper
                else -1
                if close[position] < prior_lower
                else state.trend
            )
            state.upper = (
                min(proposed_upper, prior_upper)
                if prior_close < prior_upper
                else proposed_upper
            )
            state.lower = (
                max(proposed_lower, prior_lower)
                if prior_close > prior_lower
                else proposed_lower
            )
        if position and math.isfinite(state.output):
            direction = float(np.sign(prior_close - state.output))
            realized = (close[position] - prior_close) * direction
            state.performance += alpha * (realized - state.performance)
        state.output = state.lower if state.trend == 1 else state.upper


def _best_cluster_factor(
    performance: NDArray[np.float64],
    factors: NDArray[np.float64],
    maximum_iterations: int,
) -> float:
    if len(performance) == 1 or np.allclose(performance, performance[0]):
        return float(np.mean(factors))
    centroids = np.percentile(performance, [25.0, 50.0, 75.0])
    assignments = np.zeros(len(performance), dtype=np.int8)
    for _ in range(maximum_iterations):
        distances = np.abs(performance[:, None] - centroids[None, :])
        assignments = np.argmin(distances, axis=1).astype(np.int8)
        updated = centroids.copy()
        for cluster in range(3):
            members = performance[assignments == cluster]
            if len(members):
                updated[cluster] = float(members.mean())
        if np.allclose(updated, centroids, rtol=0.0, atol=1e-12):
            break
        centroids = updated
    best = int(np.argmax(centroids))
    members = factors[assignments == best]
    if not len(members):
        members = factors[np.isclose(performance, performance.max())]
    return float(members.mean())


def _update_target(
    state: _TargetState,
    factor: float,
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    atr: NDArray[np.float64],
    position: int,
) -> tuple[float, np.int8]:
    midpoint = (high[position] + low[position]) / 2.0
    proposed_upper = midpoint + atr[position] * factor
    proposed_lower = midpoint - atr[position] * factor
    prior_close = close[position - 1] if position else close[position]
    if not math.isfinite(state.upper):
        state.upper, state.lower = proposed_upper, proposed_lower
    else:
        prior_upper, prior_lower = state.upper, state.lower
        state.trend = (
            1
            if close[position] > prior_upper
            else -1
            if close[position] < prior_lower
            else state.trend
        )
        state.upper = (
            min(proposed_upper, prior_upper)
            if prior_close < prior_upper
            else proposed_upper
        )
        state.lower = (
            max(proposed_lower, prior_lower)
            if prior_close > prior_lower
            else proposed_lower
        )
    trail = state.lower if state.trend == 1 else state.upper
    return trail, np.int8(state.trend)
