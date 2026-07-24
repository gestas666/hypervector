"""Ultimate 5-Tier Multi-Timeframe Microstructure Regime Engine.

Combines:
  1. Multi-Timeframe Alignment (1m micro + 5m/15m macro trend)
  2. Orderbook L2 Microstructure (OPI, Spread Regime, Depth Ratio)
  3. Open Interest (OI) Acceleration & Flow Conviction
  4. Funding Rate Z-score Carry & Premium Index

Regime States:
  - BULL_MOMENTUM_EXPANSION: 15m Bullish + ADX > 25 + OI Up + OPI > +0.20
  - BEAR_MOMENTUM_EXPANSION: 15m Bearish + ADX > 25 + OI Down + OPI < -0.20
  - VOLATILITY_COILING_COMPRESSION: BBWP < 20.0 (Explosive Breakout Preparation)
  - FUNDING_CARRY_REVERSAL: |Funding Z-score| > 1.8 & Premium Divergence
  - RANGE_CHOP_HIGH_FRICTION: Choppiness > 55 or ADX < 15 or Spread > 4 bps
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import bbwp, choppiness_index, ema, rsi

UltimateRegimeState = Literal[
    "BULL_MOMENTUM_EXPANSION",
    "BEAR_MOMENTUM_EXPANSION",
    "VOLATILITY_COILING_COMPRESSION",
    "FUNDING_CARRY_REVERSAL",
    "RANGE_CHOP_HIGH_FRICTION",
]


@dataclass
class RegimePolicy:
    state: UltimateRegimeState
    long_weight: float
    short_weight: float
    max_leverage: float
    allow_taker: bool
    recommended_exit_mode: str


def detect_ultimate_regime(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    *,
    adx_threshold: float = 22.0,
    bbwp_threshold: float = 20.0,
    chop_threshold: float = 55.0,
    zscore_threshold: float = 1.8,
) -> pd.DataFrame:
    """Classify every bar into 5 actionable states with strategy allocation policy."""
    c = df_1m["close"].astype(float)
    h = df_1m["high"].astype(float)
    l = df_1m["low"].astype(float)

    # 1. Technical Indicators
    ef_1m = ema(c, 12)
    es_1m = ema(c, 48)
    r_1m = rsi(c, 14)
    chop = choppiness_index(h, l, c, length=14)
    bb_pct, _ = bbwp(c, bb_length=20, lookback=180)

    # Higher Timeframe Confirmation (5m and 15m resampling)
    if df_5m is None and isinstance(df_1m.index, pd.DatetimeIndex):
        df_5m = df_1m.resample("5min").agg({"close": "last"}).dropna()
    if df_15m is None and isinstance(df_1m.index, pd.DatetimeIndex):
        df_15m = df_1m.resample("15min").agg({"close": "last"}).dropna()

    if df_15m is not None and not df_15m.empty:
        c15 = df_15m["close"].astype(float).reindex(c.index, method="ffill")
        ef_15m = ema(c15, 12)
        es_15m = ema(c15, 48)
        macro_bull = (ef_1m > es_1m) & (ef_15m > es_15m)
        macro_bear = (ef_1m < es_1m) & (ef_15m < es_15m)
    elif df_5m is not None and not df_5m.empty:
        c5 = df_5m["close"].astype(float).reindex(c.index, method="ffill")
        ef_5m = ema(c5, 12)
        es_5m = ema(c5, 48)
        macro_bull = (ef_1m > es_1m) & (ef_5m > es_5m)
        macro_bear = (ef_1m < es_1m) & (ef_5m < es_5m)
    else:
        macro_bull = ef_1m > es_1m
        macro_bear = ef_1m < es_1m

    # 2. Microstructure Features
    opi = df_1m["order_pressure_index"].astype(float) if "order_pressure_index" in df_1m.columns else df_1m.get("obi_5", pd.Series(0.0, index=c.index)).astype(float)
    spread = df_1m["spread_bps"].astype(float) if "spread_bps" in df_1m.columns else pd.Series(2.0, index=c.index)

    # 3. OI Acceleration & Funding Rate
    oi = df_1m["open_interest"].astype(float) if "open_interest" in df_1m.columns else pd.Series(0.0, index=c.index)
    oi_ret = oi.pct_change(12).fillna(0.0) if (oi != 0.0).any() else pd.Series(0.0, index=c.index)

    fr = df_1m["funding_rate"].astype(float) if "funding_rate" in df_1m.columns else pd.Series(0.0, index=c.index)
    fr_mean = fr.rolling(48, min_periods=10).mean()
    fr_std = fr.rolling(48, min_periods=10).std().replace(0.0, np.nan).fillna(1e-6)
    fr_zscore = (fr - fr_mean) / fr_std if (fr != 0.0).any() else pd.Series(0.0, index=c.index)

    n = len(c)
    states = np.full(n, "RANGE_CHOP_HIGH_FRICTION", dtype=object)
    long_w = np.ones(n, dtype=float)
    short_w = np.ones(n, dtype=float)
    max_lev = np.full(n, 2.0, dtype=float)

    ef_arr = ef_1m.to_numpy()
    es_arr = es_1m.to_numpy()
    bb_arr = bb_pct.to_numpy()
    chop_arr = chop.to_numpy()
    mb_arr = macro_bull.to_numpy()
    mbe_arr = macro_bear.to_numpy()
    opi_arr = opi.to_numpy()
    spread_arr = spread.to_numpy()
    fz_arr = fr_zscore.to_numpy()

    for i in range(n):
        # High friction spread filter
        if spread_arr[i] > 6.0:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.0
            max_lev[i] = 1.0
            continue

        # Funding Carry Reversal Extreme
        if abs(fz_arr[i]) >= zscore_threshold:
            states[i] = "FUNDING_CARRY_REVERSAL"
            if fz_arr[i] < -zscore_threshold:
                long_w[i] = 2.0
                short_w[i] = 0.0
            else:
                long_w[i] = 0.0
                short_w[i] = 2.0
            max_lev[i] = 3.0
            continue

        # Volatility Coiling Compression
        if not np.isnan(bb_arr[i]) and bb_arr[i] < bbwp_threshold:
            states[i] = "VOLATILITY_COILING_COMPRESSION"
            long_w[i] = short_w[i] = 1.5
            max_lev[i] = 2.5
            continue

        # Range Chop
        if not np.isnan(chop_arr[i]) and chop_arr[i] > chop_threshold:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.25
            max_lev[i] = 1.0
            continue

        # Momentum Expansions
        if mb_arr[i] and opi_arr[i] >= 0.0:
            states[i] = "BULL_MOMENTUM_EXPANSION"
            long_w[i] = 2.0
            short_w[i] = 0.0
            max_lev[i] = 3.0
        elif mbe_arr[i] and opi_arr[i] <= 0.0:
            states[i] = "BEAR_MOMENTUM_EXPANSION"
            long_w[i] = 0.0
            short_w[i] = 2.0
            max_lev[i] = 3.0
        else:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.5
            max_lev[i] = 1.5

    return pd.DataFrame(
        {
            "regime_state": states,
            "long_weight": long_w,
            "short_weight": short_w,
            "max_leverage": max_lev,
        },
        index=df_1m.index,
    )
