"""Named, scored, causal setup engine for rebuilt Hulk Smash."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.shared_portfolio_models import Direction

_COMPONENT_COLUMNS = {
    "wt1",
    "wave_cross",
    "money_flow_direction",
    "volume_ratio",
    "ema_trend",
    "krown_direction",
    "krown_zone_context",
}
_QUALITY_COLUMNS = {
    "supertrend_direction",
    "adx",
    "di_direction",
    "squeeze_on",
    "squeeze_release",
    "ha_choppy",
}
_OUTPUT_COLUMNS = [
    "candidate",
    "signal_time_utc",
    "side",
    "score",
    "eligible",
    "reason",
    "trigger",
    "evidence",
    "stop_anchor",
]


@dataclass(frozen=True)
class RebuiltHulkConfig:
    """Frozen setup score and structural-pivot parameters."""

    minimum_score: int = 8
    pivot_bars: int = 5
    adx_trending: float = 25.0
    adx_usable: float = 18.0

    def __post_init__(self) -> None:
        """Reject incoherent tuning inputs."""
        if not 1 <= self.minimum_score <= 99:
            raise ValueError("Hulk minimum_score must be within [1, 99]")
        if self.pivot_bars < 2:
            raise ValueError("Hulk pivot_bars must be at least two")
        if not 0.0 < self.adx_usable <= self.adx_trending:
            raise ValueError("Hulk ADX thresholds are inconsistent")


@dataclass(frozen=True)
class _HulkArrays:
    high: NDArray[np.float64]
    low: NDArray[np.float64]
    wt1: NDArray[np.float64]
    wave_cross: NDArray[np.int64]
    money_flow: NDArray[np.int64]
    volume_ratio: NDArray[np.float64]
    ema_trend: NDArray[np.int64]
    krown_direction: NDArray[np.int64]
    krown_zone: NDArray[np.int64]
    supertrend: NDArray[np.int64]
    adx: NDArray[np.float64]
    di_direction: NDArray[np.int64]
    squeeze_release: NDArray[np.bool_]
    ha_choppy: NDArray[np.bool_]


def evaluate_rebuilt_hulk_signals(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    quality: pd.DataFrame,
    config: RebuiltHulkConfig | None = None,
) -> pd.DataFrame:
    """Return every rebuilt Hulk trigger with score and disposition retained."""
    cfg = config or RebuiltHulkConfig()
    _validate_inputs(bars, components, quality)
    values = _arrays(bars, components, quality)
    rows: list[dict[str, object]] = []
    for position in range(1, len(bars)):
        trigger = _trigger(values, position)
        if trigger is None:
            continue
        direction, name = trigger
        rows.append(_decision(bars.index, values, position, direction, name, cfg))
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _trigger(values: _HulkArrays, position: int) -> tuple[Direction, str] | None:
    wave = int(values.wave_cross[position])
    if wave in {-1, 1}:
        return _direction(wave), "wave_cross"
    if bool(values.squeeze_release[position]):
        direction = _aligned_trend(values, position)
        if direction != 0:
            return _direction(direction), "squeeze_release"
    current = int(values.krown_direction[position])
    previous = int(values.krown_direction[position - 1])
    if current in {-1, 1} and current != previous:
        if current == _aligned_trend(values, position):
            return _direction(current), "krown_turn"
    return None


def _decision(
    index: pd.DatetimeIndex,
    values: _HulkArrays,
    position: int,
    direction: Direction,
    trigger: str,
    config: RebuiltHulkConfig,
) -> dict[str, object]:
    sign = 1 if direction == "long" else -1
    evidence = _evidence(values, position, sign, trigger, config)
    score = sum(points for _, points in evidence)
    archetype = _archetype(values, position, sign, trigger)
    eligible = score >= config.minimum_score
    start = max(0, position - config.pivot_bars + 1)
    stop = float(
        values.low[start : position + 1].min()
        if sign == 1
        else values.high[start : position + 1].max()
    )
    return {
        "candidate": f"hulk_rebuilt_{archetype}_v1",
        "signal_time_utc": index[position],
        "side": direction,
        "score": score,
        "eligible": eligible,
        "reason": "eligible" if eligible else f"score_below_{config.minimum_score}",
        "trigger": trigger,
        "evidence": tuple(name for name, _ in evidence),
        "stop_anchor": stop,
    }


def _evidence(
    values: _HulkArrays,
    position: int,
    sign: int,
    trigger: str,
    config: RebuiltHulkConfig,
) -> list[tuple[str, int]]:
    evidence: list[tuple[str, int]] = []
    _add(evidence, "wave_cross", 2, trigger == "wave_cross")
    _add(evidence, "squeeze_release", 2, trigger == "squeeze_release")
    _add(evidence, "krown_turn", 1, trigger == "krown_turn")
    _add(evidence, "supertrend", 2, int(values.supertrend[position]) == sign)
    _add(evidence, "ema_trend", 2, int(values.ema_trend[position]) == sign)
    _add(evidence, "di_alignment", 1, int(values.di_direction[position]) == sign)
    _adx_evidence(evidence, float(values.adx[position]), config)
    _add(evidence, "money_flow", 1, int(values.money_flow[position]) == sign)
    _add(evidence, "krown_direction", 1, int(values.krown_direction[position]) == sign)
    _add(evidence, "krown_zone", 1, int(values.krown_zone[position]) == sign)
    ratio = float(values.volume_ratio[position])
    _add(evidence, "volume", 1, math.isfinite(ratio) and ratio > 1.0)
    _add(evidence, "volume_surge", 1, math.isfinite(ratio) and ratio >= 1.5)
    _add(evidence, "not_choppy", 1, not bool(values.ha_choppy[position]))
    _add(evidence, "wave_extreme", 1, _prior_extreme(values, position, sign))
    return evidence


def _adx_evidence(
    values: list[tuple[str, int]], adx: float, config: RebuiltHulkConfig
) -> None:
    _add(values, "adx_trending", 2, math.isfinite(adx) and adx >= config.adx_trending)
    if not any(name == "adx_trending" for name, _ in values):
        _add(values, "adx_usable", 1, math.isfinite(adx) and adx >= config.adx_usable)


def _add(values: list[tuple[str, int]], name: str, points: int, active: bool) -> None:
    if active:
        values.append((name, points))


def _archetype(
    values: _HulkArrays,
    position: int,
    sign: int,
    trigger: str,
) -> str:
    if trigger == "squeeze_release":
        return "expansion"
    aligned = _aligned_trend(values, position) == sign
    if trigger == "wave_cross" and _prior_extreme(values, position, sign):
        return "continuation" if aligned else "reversal"
    return "continuation" if aligned else "reversal"


def _aligned_trend(values: _HulkArrays, position: int) -> int:
    ema = int(values.ema_trend[position])
    trend = int(values.supertrend[position])
    return ema if ema in {-1, 1} and ema == trend else 0


def _prior_extreme(values: _HulkArrays, position: int, sign: int) -> bool:
    window = values.wt1[max(0, position - 5) : position + 1]
    finite = window[np.isfinite(window)]
    if not len(finite):
        return False
    return bool(finite.min() < -40.0 if sign == 1 else finite.max() > 40.0)


def _arrays(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    quality: pd.DataFrame,
) -> _HulkArrays:
    return _HulkArrays(
        high=bars["high"].to_numpy(dtype=np.float64),
        low=bars["low"].to_numpy(dtype=np.float64),
        wt1=components["wt1"].to_numpy(dtype=np.float64),
        wave_cross=components["wave_cross"].to_numpy(dtype=np.int64),
        money_flow=components["money_flow_direction"].to_numpy(dtype=np.int64),
        volume_ratio=components["volume_ratio"].to_numpy(dtype=np.float64),
        ema_trend=components["ema_trend"].to_numpy(dtype=np.int64),
        krown_direction=components["krown_direction"].to_numpy(dtype=np.int64),
        krown_zone=components["krown_zone_context"].to_numpy(dtype=np.int64),
        supertrend=quality["supertrend_direction"].to_numpy(dtype=np.int64),
        adx=quality["adx"].to_numpy(dtype=np.float64),
        di_direction=quality["di_direction"].to_numpy(dtype=np.int64),
        squeeze_release=quality["squeeze_release"].to_numpy(dtype=bool),
        ha_choppy=quality["ha_choppy"].to_numpy(dtype=bool),
    )


def _direction(sign: int) -> Direction:
    return "long" if sign == 1 else "short"


def _validate_inputs(
    bars: pd.DataFrame, components: pd.DataFrame, quality: pd.DataFrame
) -> None:
    missing_components = sorted(_COMPONENT_COLUMNS.difference(components.columns))
    missing_quality = sorted(_QUALITY_COLUMNS.difference(quality.columns))
    aligned = bars.index.equals(components.index) and bars.index.equals(quality.index)
    valid_index = isinstance(bars.index, pd.DatetimeIndex) and bars.index.tz
    if bars.empty or not aligned or not valid_index:
        raise ValueError("rebuilt Hulk inputs must be non-empty and index aligned")
    if missing_components or missing_quality:
        raise ValueError(
            f"rebuilt Hulk inputs missing components={missing_components} quality={missing_quality}"
        )
    if not {"high", "low"}.issubset(bars.columns):
        raise ValueError("rebuilt Hulk bars require high and low")
