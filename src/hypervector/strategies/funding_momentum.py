"""Funding Rate Z-Score & Carry Yield Strategy (Enhanced).

Thesis:
  - Long Entry: Funding Z-Score < -1.5 (Shorts paying Longs heavily) & Fast EMA > Slow EMA
  - Short Entry: Funding Z-Score > +1.5 (Longs paying Shorts heavily) & Fast EMA < Slow EMA
  - Carry Multiplier: Dynamically scales conviction when funding yield is extreme
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hypervector.data.book_align import gate_signals_by_orderbook
from hypervector.strategies.indicators import ema
from hypervector.strategies.registry import StrategySpec, register


def build_funding_momentum_long_signals(
    df: pd.DataFrame,
    *,
    lookback: int = 48,
    zscore_entry: float = 1.5,
    zscore_exit: float = 0.5,
    regime_filter: bool = True,
    book_gate: bool = False,
    max_spread_bps: float = 5.0,
    min_obi: float = 0.0,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Build Funding Rate Z-score Long Signals with Carry Yield confirmation."""
    c = df["close"].astype(float)
    fr = (
        df["funding_rate"].astype(float)
        if "funding_rate" in df.columns
        else pd.Series(0.0, index=df.index)
    )

    # Funding Z-score
    fr_mean = fr.rolling(lookback, min_periods=10).mean()
    fr_std = (
        fr.rolling(lookback, min_periods=10).std().replace(0.0, np.nan).fillna(1e-6)
    )
    zscore = (fr - fr_mean) / fr_std

    # Trend confirmation
    ef = ema(c, 12)
    es = ema(c, 26)
    regime = (ef > es) if regime_filter else pd.Series(True, index=df.index)

    # Long when funding is heavily negative (shorts pay longs)
    raw_entries = (zscore < -zscore_entry) & regime

    if book_gate and ({"spread_bps", "obi_5"}.issubset(df.columns)):
        entries = gate_signals_by_orderbook(
            raw_entries,
            df,
            direction="long",
            max_spread_bps=max_spread_bps,
            min_obi=min_obi,
        )
    else:
        entries = raw_entries

    # Exit when funding normalizes toward mean
    exits = zscore > -zscore_exit
    return entries, exits, "long"


def build_funding_momentum_short_signals(
    df: pd.DataFrame,
    *,
    lookback: int = 48,
    zscore_entry: float = 1.5,
    zscore_exit: float = 0.5,
    regime_filter: bool = True,
    book_gate: bool = False,
    max_spread_bps: float = 5.0,
    min_obi: float = -0.0,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Build Funding Rate Z-score Short Signals."""
    c = df["close"].astype(float)
    fr = (
        df["funding_rate"].astype(float)
        if "funding_rate" in df.columns
        else pd.Series(0.0, index=df.index)
    )

    fr_mean = fr.rolling(lookback, min_periods=10).mean()
    fr_std = (
        fr.rolling(lookback, min_periods=10).std().replace(0.0, np.nan).fillna(1e-6)
    )
    zscore = (fr - fr_mean) / fr_std

    ef = ema(c, 12)
    es = ema(c, 26)
    regime = (ef < es) if regime_filter else pd.Series(True, index=df.index)

    raw_entries = (zscore > zscore_entry) & regime

    if book_gate and ({"spread_bps", "obi_5"}.issubset(df.columns)):
        entries = gate_signals_by_orderbook(
            raw_entries,
            df,
            direction="short",
            max_spread_bps=max_spread_bps,
            min_obi=min_obi,
        )
    else:
        entries = raw_entries

    exits = zscore < zscore_exit
    return entries, exits, "short"


def register_funding_momentum() -> None:
    """Register Funding Momentum strategies into global registry."""
    register(
        StrategySpec(
            name="funding_momentum_long",
            role="uptrend",
            param_grid={"lookback": [24, 48, 96], "zscore_entry": [1.2, 1.5, 2.0]},
            build_signals=build_funding_momentum_long_signals,
            description="Funding Rate Z-Score Carry & Mean Reversion Long Strategy",
        )
    )
    register(
        StrategySpec(
            name="funding_momentum_short",
            role="downtrend",
            param_grid={"lookback": [24, 48, 96], "zscore_entry": [1.2, 1.5, 2.0]},
            build_signals=build_funding_momentum_short_signals,
            description="Funding Rate Z-Score Carry & Mean Reversion Short Strategy",
        )
    )
