"""Gap-aware literal Swing Auto signals in the Heikin-Ashi chart domain."""

from __future__ import annotations

import pandas as pd

from hypervector.research.swing_ha_chart_signals import (
    build_swing_ha_chart_signals,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def build_gap_aware_swing_ha_signals(
    bars: pd.DataFrame,
    config: SwingHaSignalConfig,
    *,
    timeframe: str = "15m",
) -> pd.DataFrame:
    """Build segment-reset signals and expire entries across archive outages."""
    _validate_gap_bars(bars)
    _validate_timeframe(timeframe)
    segment_ids = bars["gap_before_bars"].gt(0).cumsum().astype(int)
    frames: list[pd.DataFrame] = []
    warmup_bars = max(config.slow_ema, config.pivot_length * 2 + 1)
    for segment_id, segment in bars.groupby(segment_ids, sort=True):
        signals = build_swing_ha_chart_signals(segment, config)
        signals["long_signal_name"] = f"swing_ha_chart_long@{timeframe}"
        signals["short_signal_name"] = f"swing_ha_chart_short@{timeframe}"
        signals["source_segment_id"] = int(segment_id)
        positions = pd.Series(range(len(signals)), index=signals.index)
        signals["signal_warmup"] = positions.lt(warmup_bars)
        signals.loc[signals["signal_warmup"], ["long_entry", "short_entry"]] = False
        frames.append(signals)
    output = pd.concat(frames).sort_index()
    recovery = bars["gap_before_bars"].gt(0).reindex(output.index, fill_value=False)
    output["gap_recovery_exit"] = recovery.astype(bool)
    output.loc[recovery, ["long_exit", "short_exit"]] = True
    output["entry_expired_across_gap"] = False
    output["execution_authority"] = "none"
    return output


def _validate_timeframe(timeframe: str) -> None:
    if timeframe not in {"5m", "15m"}:
        raise ValueError("HIP-3 Swing/HA timeframe must be 5m or 15m")


def _validate_gap_bars(bars: pd.DataFrame) -> None:
    if "gap_before_bars" not in bars:
        raise ValueError("HIP-3 Swing/HA bars require gap_before_bars")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("HIP-3 Swing/HA bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("HIP-3 Swing/HA bars require ordered unique rows")
    gaps = pd.to_numeric(bars["gap_before_bars"], errors="raise")
    if gaps.isna().any() or gaps.lt(0).any() or not gaps.mod(1).eq(0).all():
        raise ValueError("gap_before_bars must contain non-negative integers")
