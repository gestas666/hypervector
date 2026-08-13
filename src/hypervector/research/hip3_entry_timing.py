"""Causal report-only entry-timing variants for HIP-3 Swing signals."""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

from hypervector.research.swing_ha_signals import EntryMode


class Hip3EntryTimingMode(str, Enum):
    """Supported entry clocks that retain the native directional identity."""

    PROVIDER_EXACT = "provider_exact"
    ALIGNMENT_ONSET = "alignment_onset"
    NEXT_BAR_CONFIRMATION = "next_bar_confirmation"
    FIRST_FAST_EMA_PULLBACK = "first_fast_ema_pullback"


def build_hip3_entry_timing_signals(
    bars: pd.DataFrame,
    provider_signals: pd.DataFrame,
    mode: Hip3EntryTimingMode,
    *,
    provider_entry_mode: EntryMode,
) -> pd.DataFrame:
    """Return a causal timing arm with no execution or promotion authority."""
    _validate_inputs(bars, provider_signals, mode, provider_entry_mode)
    output = provider_signals.copy()
    provider_long = output["long_entry"].astype(bool)
    provider_short = output["short_entry"].astype(bool)
    long_anchor = _anchors(provider_long, provider_entry_mode)
    short_anchor = _anchors(provider_short, provider_entry_mode)
    if mode is Hip3EntryTimingMode.PROVIDER_EXACT:
        long_entry, short_entry = provider_long, provider_short
    elif mode is Hip3EntryTimingMode.ALIGNMENT_ONSET:
        long_entry, short_entry = long_anchor, short_anchor
    elif mode is Hip3EntryTimingMode.NEXT_BAR_CONFIRMATION:
        long_entry = _confirmed_entry(long_anchor, output["long_alignment"], bars)
        short_entry = _confirmed_entry(short_anchor, output["short_alignment"], bars)
    else:
        long_entry = _first_pullback_entry(
            bars,
            output,
            anchors=long_anchor,
            alignment=output["long_alignment"],
        )
        short_entry = _first_pullback_entry(
            bars,
            output,
            anchors=short_anchor,
            alignment=output["short_alignment"],
        )
    output["provider_long_entry"] = provider_long
    output["provider_short_entry"] = provider_short
    output["timing_long_anchor"] = long_anchor
    output["timing_short_anchor"] = short_anchor
    output["long_entry"] = long_entry
    output["short_entry"] = short_entry
    output["entry_timing_mode"] = mode.value
    output["execution_authority"] = "none"
    return output


def _confirmed_entry(
    anchors: pd.Series,
    alignment: pd.Series,
    bars: pd.DataFrame,
) -> pd.Series:
    no_gap = bars["gap_before_bars"].eq(0)
    return anchors.shift(1, fill_value=False) & alignment.astype(bool) & no_gap


def _first_pullback_entry(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    anchors: pd.Series,
    alignment: pd.Series,
) -> pd.Series:
    entries = np.zeros(len(bars), dtype=bool)
    active = False
    for position in range(len(bars)):
        if bool(anchors.iloc[position]):
            active = True
            continue
        if int(bars["gap_before_bars"].iloc[position]) > 0:
            active = False
            continue
        if not bool(alignment.iloc[position]):
            active = False
            continue
        if active and _touches_fast_ema(bars, signals, position):
            entries[position] = True
            active = False
    return pd.Series(entries, index=bars.index, dtype=bool)


def _touches_fast_ema(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    position: int,
) -> bool:
    ema = float(signals["ema_fast"].iloc[position])
    low = float(bars["low"].iloc[position])
    high = float(bars["high"].iloc[position])
    return low <= ema <= high


def _onset(state: pd.Series) -> pd.Series:
    return state & ~state.shift(1, fill_value=False)


def _anchors(provider_entries: pd.Series, entry_mode: EntryMode) -> pd.Series:
    if entry_mode == "onset":
        return provider_entries.copy()
    return _onset(provider_entries)


def _validate_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    mode: Hip3EntryTimingMode,
    provider_entry_mode: EntryMode,
) -> None:
    if not isinstance(mode, Hip3EntryTimingMode):
        raise ValueError("unsupported HIP-3 entry timing mode")
    if provider_entry_mode not in {"state", "onset"}:
        raise ValueError("provider_entry_mode must be state or onset")
    if not bars.index.equals(signals.index):
        raise ValueError("HIP-3 entry timing bars and signals require the same index")
    required_bars = {"open", "high", "low", "close", "gap_before_bars"}
    required_signals = {
        "long_alignment",
        "short_alignment",
        "long_entry",
        "short_entry",
        "long_exit",
        "short_exit",
        "ema_fast",
    }
    missing = sorted(
        required_bars.difference(bars.columns)
        | required_signals.difference(signals.columns)
    )
    if missing:
        raise ValueError(f"HIP-3 entry timing inputs missing columns: {missing}")
    if bars.empty or not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("HIP-3 entry timing requires non-empty datetime bars")
    if bars.index.tz is None or not bars.index.is_monotonic_increasing:
        raise ValueError("HIP-3 entry timing requires ordered timezone-aware bars")
    prices = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    ema = signals["ema_fast"].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError("HIP-3 entry timing prices must be finite and positive")
    aligned = signals[["long_alignment", "short_alignment"]].any(axis=1).to_numpy()
    invalid_aligned_ema = aligned & (~np.isfinite(ema) | (ema <= 0.0))
    if np.isinf(ema).any() or invalid_aligned_ema.any():
        raise ValueError(
            "HIP-3 entry timing EMA must be finite and positive when aligned"
        )
    gaps = bars["gap_before_bars"].to_numpy(dtype=float)
    if not np.isfinite(gaps).all() or (gaps < 0.0).any():
        raise ValueError("HIP-3 entry timing gaps must be finite and non-negative")
