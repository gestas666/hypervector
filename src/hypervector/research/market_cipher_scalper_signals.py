"""Deterministic reconstruction of the prompt-only MC 15m Scalper entries."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


_COMPONENT_COLUMNS = {
    "wave_cross",
    "money_flow_direction",
    "price_vwap_alignment",
    "volume_ratio",
    "volume_surge",
    "stoch_k",
}
_OUTPUT_COLUMNS = [
    "candidate",
    "signal_time_utc",
    "side",
    "score",
    "eligible",
    "reason",
    "money_flow_confirmed",
    "vwap_aligned",
    "volume_confirmed",
    "htf_level_clear",
    "one_hour_trend",
    "stop_anchor",
]


def evaluate_mc_scalper_signals(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    one_hour_trend: pd.Series,
    near_major_htf_level: pd.Series,
) -> pd.DataFrame:
    """Evaluate every 15m WaveTrend cross and retain rejected decisions."""
    _validate_inputs(bars, components, one_hour_trend, near_major_htf_level)
    rows = [
        _decision(
            position,
            int(components.iloc[position]["wave_cross"]),
            bars,
            components,
            one_hour_trend,
            near_major_htf_level,
        )
        for position in np.flatnonzero(components["wave_cross"].to_numpy() != 0)
    ]
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def _decision(
    position: int,
    direction: int,
    bars: pd.DataFrame,
    components: pd.DataFrame,
    one_hour_trend: pd.Series,
    near_level: pd.Series,
) -> dict[str, object]:
    """Build one transparent scored cross decision."""
    side = "long" if direction == 1 else "short"
    flow = _flow_confirmed(components, position, direction)
    vwap = int(components.iloc[position]["price_vwap_alignment"]) == direction
    ratio = float(components.iloc[position]["volume_ratio"])
    volume = math.isfinite(ratio) and ratio > 1.0
    level_value = near_level.iloc[position]
    level_clear = not pd.isna(level_value) and not bool(level_value)
    hourly = int(one_hour_trend.iloc[position])
    stoch = float(components.iloc[position]["stoch_k"])
    score = _score(flow, vwap, ratio, hourly, direction, stoch)
    reasons = _reasons(flow, vwap, volume, level_value, hourly, direction, score)
    eligible = not reasons
    stop = float(bars.iloc[position]["low" if direction == 1 else "high"])
    return {
        "candidate": "mc_scalper_15m",
        "signal_time_utc": components.index[position],
        "side": side,
        "score": score,
        "eligible": eligible,
        "reason": "eligible" if eligible else ",".join(reasons),
        "money_flow_confirmed": flow,
        "vwap_aligned": vwap,
        "volume_confirmed": volume,
        "htf_level_clear": level_clear,
        "one_hour_trend": hourly,
        "stop_anchor": stop,
    }


def _flow_confirmed(components: pd.DataFrame, position: int, direction: int) -> bool:
    """Return whether RSI+MFI area agreed within three completed bars."""
    start = max(0, position - 2)
    values = components["money_flow_direction"].iloc[start : position + 1]
    return bool(values.eq(direction).any())


def _score(
    flow: bool,
    vwap: bool,
    volume_ratio: float,
    hourly: int,
    direction: int,
    stoch: float,
) -> int:
    """Apply the recovered ten-point score without discretionary weights."""
    score = 3 + (2 if flow else 0) + (1 if vwap else 0)
    score += 1 if math.isfinite(volume_ratio) and volume_ratio > 1.5 else 0
    score += 2 if hourly == direction else 0
    extreme = math.isfinite(stoch) and (
        (direction == 1 and stoch < 20.0) or (direction == -1 and stoch > 80.0)
    )
    return score + (1 if extreme else 0)


def _reasons(
    flow: bool,
    vwap: bool,
    volume: bool,
    level_value: object,
    hourly: int,
    direction: int,
    score: int,
) -> list[str]:
    """Return all failed mechanical conditions for telemetry."""
    reasons: list[str] = []
    if not flow:
        reasons.append("money_flow_not_confirmed")
    if not vwap:
        reasons.append("vwap_not_aligned")
    if not volume:
        reasons.append("volume_not_above_average")
    if pd.isna(level_value):
        reasons.append("htf_level_unavailable")
    elif bool(level_value):
        reasons.append("near_major_htf_level")
    if hourly == -direction:
        reasons.append("opposite_1h_trend")
    if score < 7:
        reasons.append("score_below_7")
    return reasons


def _validate_inputs(
    bars: pd.DataFrame,
    components: pd.DataFrame,
    one_hour_trend: pd.Series,
    near_level: pd.Series,
) -> None:
    """Validate aligned causal inputs for signal evaluation."""
    missing_bars = sorted({"high", "low"}.difference(bars.columns))
    missing_components = sorted(_COMPONENT_COLUMNS.difference(components.columns))
    if missing_bars or missing_components:
        raise ValueError(
            f"MC scalper inputs missing bars={missing_bars} components={missing_components}"
        )
    index = components.index
    aligned = bars.index.equals(index) and one_hour_trend.index.equals(index)
    aligned = aligned and near_level.index.equals(index)
    if components.empty or not aligned:
        raise ValueError("MC scalper inputs must be non-empty and index aligned")
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("MC scalper decisions require a timezone-aware index")
