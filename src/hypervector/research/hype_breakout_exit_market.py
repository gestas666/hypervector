"""Build historical HYPE exit-replay inputs from the exact live entry source."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import pandas as pd

from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.range_onset_observation import index_range_onset_bars
from hypervector.research.range_onset_signals import build_range_onset_signals

_MINUTE = pd.Timedelta(minutes=1)
_SIGNAL_FEATURE_COLUMNS = ("sma_gap_bps",)
_REGIME_FEATURE_COLUMNS = (
    "state_1m",
    "context_15m",
    "regime_strength_score",
    "bbwp_percentile",
    "ema_gap_bps_signed",
    "rsi",
    "breakout_volume_ratio",
    "regime_5m_strength_percentile",
    "regime_5m_bbwp_percentile",
    "regime_5m_ema_gap_bps",
    "regime_5m_rsi",
    "regime_5m_rsi_ema",
    "regime_5m_breakout_volume_ratio",
)
EntryDirectionMode = Literal["structural", "breakout"]


@dataclass(frozen=True)
class HypeExitMarketEvidence:
    """Data coverage and exact entry counts for one reconstructed market."""

    start_utc: str
    end_utc: str
    bar_rows: int
    breakout_onsets: int
    directional_entry_signals: int
    long_entry_signals: int
    short_entry_signals: int
    funding_events_supplied: int
    funding_events_matched: int


def build_hype_exit_market(
    raw_bars: pd.DataFrame,
    funding: pd.DataFrame,
    *,
    entry_direction_mode: EntryDirectionMode = "structural",
) -> tuple[pd.DataFrame, HypeExitMarketEvidence]:
    """Reconstruct live-parity entry states over a complete historical window."""
    bars = index_range_onset_bars(raw_bars)
    _validate_minute_cadence(bars)
    signals = build_range_onset_signals(bars)
    regimes = classify_multitimeframe(bars)
    return assemble_hype_exit_market(
        bars,
        signals,
        regimes,
        funding,
        entry_direction_mode=entry_direction_mode,
    )


def assemble_hype_exit_market(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
    funding: pd.DataFrame,
    *,
    entry_direction_mode: EntryDirectionMode = "structural",
) -> tuple[pd.DataFrame, HypeExitMarketEvidence]:
    """Align source decisions, entry onsets, and hourly funding without filling."""
    _validate_source_alignment(bars, signals, regimes)
    structural = signals["structural_direction"].astype(object)
    state_5m = regimes["state_5m"].astype(str)
    onset = state_5m.eq("BREAKOUT") & state_5m.shift().ne("BREAKOUT")
    selected_direction = _selected_entry_direction(
        structural,
        regimes,
        entry_direction_mode,
    )
    directional = selected_direction.isin(("long", "short"))
    entry = selected_direction.where(onset & directional, None)
    funding_rates, supplied, matched = _aligned_funding(bars.index, funding)
    market = bars[["open", "high", "low", "close", "volume"]].copy()
    market["entry_side"] = entry
    market["state_5m"] = state_5m
    market["structural_direction"] = structural
    if "structural_direction" in regimes:
        market["breakout_side"] = _breakout_side(regimes)
    market["funding_rate"] = funding_rates
    _attach_feature_sources(market, signals, regimes)
    evidence = _evidence(market, onset, entry, supplied, matched)
    return market, evidence


def _selected_entry_direction(
    structural: pd.Series,
    regimes: pd.DataFrame,
    mode: EntryDirectionMode,
) -> pd.Series:
    if mode == "structural":
        return structural
    if mode != "breakout":
        raise ValueError("entry_direction_mode must be structural or breakout")
    return _breakout_side(regimes)


def _breakout_side(regimes: pd.DataFrame) -> pd.Series:
    if "structural_direction" not in regimes:
        raise ValueError("breakout entry direction requires 5m structural_direction")
    breakout = regimes["structural_direction"].astype(object)
    invalid = breakout.notna() & ~breakout.isin(("long", "short"))
    if invalid.any():
        raise ValueError("unsupported 5m structural_direction value")
    return breakout.where(breakout.notna(), None)


def _attach_feature_sources(
    market: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> None:
    for column in _SIGNAL_FEATURE_COLUMNS:
        if column in signals:
            market[column] = signals[column]
    for column in _REGIME_FEATURE_COLUMNS:
        if column in regimes:
            market[column] = regimes[column]


def _validate_source_alignment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> None:
    if not bars.index.equals(signals.index) or not bars.index.equals(regimes.index):
        raise ValueError("HYPE bars, signals, and regimes must share one index")
    if "structural_direction" not in signals:
        raise ValueError("HYPE source signals require structural_direction")
    if "state_5m" not in regimes:
        raise ValueError("HYPE source regimes require state_5m")
    _validate_minute_cadence(bars)


def _validate_minute_cadence(bars: pd.DataFrame) -> None:
    if bars.empty or not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("HYPE source bars require a non-empty DatetimeIndex")
    if bars.index.tz is None or bars.index.has_duplicates:
        raise ValueError("HYPE source bar timestamps must be unique and aware")
    differences = bars.index.to_series().diff().iloc[1:]
    if not differences.eq(_MINUTE).all():
        raise ValueError("HYPE source bars require exact one-minute cadence")


def _aligned_funding(
    index: pd.DatetimeIndex,
    funding: pd.DataFrame,
) -> tuple[pd.Series, int, int]:
    output = pd.Series(0.0, index=index, dtype=float)
    if funding.empty:
        return output, 0, 0
    required = {"timestamp", "funding_rate"}
    missing = sorted(required.difference(funding.columns))
    if missing:
        raise ValueError(f"HYPE funding is missing columns: {missing}")
    timestamps = pd.to_datetime(funding["timestamp"], utc=True)
    if timestamps.duplicated().any():
        raise ValueError("HYPE funding timestamps must be unique")
    rates = funding["funding_rate"].astype(float)
    if not rates.map(math.isfinite).all():
        raise ValueError("HYPE funding rates must be finite")
    supplied = len(funding)
    matched_mask = timestamps.isin(index)
    output.loc[timestamps[matched_mask]] = rates.loc[matched_mask].to_numpy()
    return output, supplied, int(matched_mask.sum())


def _evidence(
    market: pd.DataFrame,
    onset: pd.Series,
    entry: pd.Series,
    funding_supplied: int,
    funding_matched: int,
) -> HypeExitMarketEvidence:
    return HypeExitMarketEvidence(
        market.index[0].isoformat(),
        market.index[-1].isoformat(),
        len(market),
        int(onset.sum()),
        int(entry.notna().sum()),
        int(entry.eq("long").sum()),
        int(entry.eq("short").sum()),
        funding_supplied,
        funding_matched,
    )
