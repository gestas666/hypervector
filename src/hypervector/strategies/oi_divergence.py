"""OI Divergence Strategy (Enhanced) — Institutional Flow & Open Interest Acceleration.

Thesis:
  - Long Entry: Price UP & Open Interest (OI) UP & Volume > Avg & OI Acceleration > 0
  - Short Entry: Price DOWN & OI DOWN & Volume > Avg & OI Acceleration < 0
  - Fakeout Gate: Rejects entries when Price and OI diverge (Short Squeezes / Fake Breakouts)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hypervector.data.book_align import gate_signals_by_orderbook
from hypervector.strategies.indicators import ema, rsi
from hypervector.strategies.registry import StrategySpec, register


def build_oi_divergence_long_signals(
    df: pd.DataFrame,
    *,
    lookback: int = 24,
    mom_threshold: float = 0.005,
    oi_threshold: float = 0.005,
    volume_mult: float = 1.2,
    use_acceleration: bool = True,
    regime_filter: bool = True,
    book_gate: bool = False,
    max_spread_bps: float = 5.0,
    min_obi: float = 0.0,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Build OI Agreement Long Signals with Acceleration and Volume Conviction."""
    c = df["close"].astype(float)
    v = (
        df["volume"].astype(float)
        if "volume" in df.columns
        else pd.Series(1.0, index=df.index)
    )
    oi = (
        df["open_interest"].astype(float)
        if "open_interest" in df.columns
        else pd.Series(0.0, index=df.index)
    )

    # 1. Price Momentum Return
    price_ret = c.pct_change(lookback).fillna(0.0)
    price_up = price_ret > mom_threshold

    # 2. Open Interest Change Rate & Acceleration
    oi_has_data = (oi != 0.0).any()
    if oi_has_data:
        oi_ret = oi.pct_change(lookback).fillna(0.0)
        oi_accel = oi_ret.diff(lookback // 2).fillna(0.0)
        oi_up = oi_ret > oi_threshold
        if use_acceleration:
            oi_up = oi_up & (oi_accel >= 0.0)
    else:
        oi_up = pd.Series(True, index=df.index)

    # 3. Volume Surge Filter
    vol_avg = v.rolling(lookback * 2, min_periods=5).mean().fillna(1.0)
    vol_surge = v > (vol_avg * volume_mult)

    # 4. Trend Regime Filter
    e_fast = ema(c, 12)
    e_slow = ema(c, 48)
    regime = (e_fast > e_slow) if regime_filter else pd.Series(True, index=df.index)

    raw_entries = price_up & oi_up & vol_surge & regime

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

    # Strategy Exits: Price/OI divergence or RSI overbought (> 75)
    r = rsi(c, 14)
    divergence_exit = (price_ret < 0.0) | (r > 75.0)
    exits = divergence_exit

    return entries, exits, "long"


def build_oi_divergence_short_signals(
    df: pd.DataFrame,
    *,
    lookback: int = 24,
    mom_threshold: float = 0.005,
    oi_threshold: float = 0.005,
    volume_mult: float = 1.2,
    use_acceleration: bool = True,
    regime_filter: bool = True,
    book_gate: bool = False,
    max_spread_bps: float = 5.0,
    min_obi: float = -0.0,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Build OI Agreement Short Signals with Acceleration."""
    c = df["close"].astype(float)
    v = (
        df["volume"].astype(float)
        if "volume" in df.columns
        else pd.Series(1.0, index=df.index)
    )
    oi = (
        df["open_interest"].astype(float)
        if "open_interest" in df.columns
        else pd.Series(0.0, index=df.index)
    )

    price_ret = c.pct_change(lookback).fillna(0.0)
    price_down = price_ret < -mom_threshold

    oi_has_data = (oi != 0.0).any()
    if oi_has_data:
        oi_ret = oi.pct_change(lookback).fillna(0.0)
        oi_accel = oi_ret.diff(lookback // 2).fillna(0.0)
        oi_down = oi_ret < -oi_threshold
        if use_acceleration:
            oi_down = oi_down & (oi_accel <= 0.0)
    else:
        oi_down = pd.Series(True, index=df.index)

    vol_avg = v.rolling(lookback * 2, min_periods=5).mean().fillna(1.0)
    vol_surge = v > (vol_avg * volume_mult)

    e_fast = ema(c, 12)
    e_slow = ema(c, 48)
    regime = (e_fast < e_slow) if regime_filter else pd.Series(True, index=df.index)

    raw_entries = price_down & oi_down & vol_surge & regime

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

    r = rsi(c, 14)
    divergence_exit = (price_ret > 0.0) | (r < 25.0)
    exits = divergence_exit

    return entries, exits, "short"


def register_oi_divergence() -> None:
    """Register OI Divergence strategies into global registry."""
    register(
        StrategySpec(
            name="oi_divergence_long",
            role="uptrend",
            param_grid={"lookback": [12, 24, 48], "volume_mult": [1.1, 1.3]},
            build_signals=build_oi_divergence_long_signals,
            description="Open Interest + Price Acceleration Agreement Long Strategy",
            supports_book_gate=True,
        )
    )
    register(
        StrategySpec(
            name="oi_divergence_short",
            role="downtrend",
            param_grid={"lookback": [12, 24, 48], "volume_mult": [1.1, 1.3]},
            build_signals=build_oi_divergence_short_signals,
            description="Open Interest + Price Acceleration Agreement Short Strategy",
            supports_book_gate=True,
        )
    )
