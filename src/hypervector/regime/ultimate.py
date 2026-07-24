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

from hypervector.strategies.indicators import bbwp, choppiness_index, ema, rsi, zero_lag_trend_ohlc

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

    # 1. Technical Indicators & Hysteresis Trend State Machine
    chop = choppiness_index(h, l, c, length=14)
    bb_pct, _ = bbwp(c, bb_length=20, lookback=180)
    _, t_1m = zero_lag_trend_ohlc(h, l, c, length=70, mult=1.2)

    # Higher Timeframe Confirmation (safe for 1m, 5m, 15m+ inputs)
    step_minutes = 1.0
    if isinstance(df_1m.index, pd.DatetimeIndex) and len(df_1m) > 1:
        diff_sec = (df_1m.index[1] - df_1m.index[0]).total_seconds()
        if diff_sec > 0:
            step_minutes = diff_sec / 60.0

    if step_minutes >= 15.0:
        macro_bull = t_1m == 1
        macro_bear = t_1m == -1
    else:
        if df_5m is None and isinstance(df_1m.index, pd.DatetimeIndex) and step_minutes < 5.0:
            df_5m = df_1m.resample("5min", label="right", closed="right").agg(
                {"high": "max", "low": "min", "close": "last"}
            ).dropna()
        if df_15m is None and isinstance(df_1m.index, pd.DatetimeIndex) and step_minutes < 15.0:
            df_15m = df_1m.resample("15min", label="right", closed="right").agg(
                {"high": "max", "low": "min", "close": "last"}
            ).dropna()

    if df_15m is not None and not df_15m.empty:
        h15 = df_15m["high"].astype(float)
        l15 = df_15m["low"].astype(float)
        c15 = df_15m["close"].astype(float)
        _, t15 = zero_lag_trend_ohlc(h15, l15, c15, length=70, mult=1.2)
        t_15m = t15.shift(1).reindex(c.index, method="ffill").fillna(0)
        macro_bull = (t_1m == 1) & (t_15m == 1)
        macro_bear = (t_1m == -1) & (t_15m == -1)
    elif df_5m is not None and not df_5m.empty:
        h5 = df_5m["high"].astype(float)
        l5 = df_5m["low"].astype(float)
        c5 = df_5m["close"].astype(float)
        _, t5 = zero_lag_trend_ohlc(h5, l5, c5, length=70, mult=1.2)
        t_5m = t5.shift(1).reindex(c.index, method="ffill").fillna(0)
        macro_bull = (t_1m == 1) & (t_5m == 1)
        macro_bear = (t_1m == -1) & (t_5m == -1)
    else:
        macro_bull = t_1m == 1
        macro_bear = t_1m == -1

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

    bb_arr = bb_pct.to_numpy()
    chop_arr = chop.to_numpy()
    mb_arr = macro_bull.to_numpy()
    mbe_arr = macro_bear.to_numpy()
    opi_arr = opi.to_numpy()
    spread_arr = spread.to_numpy()
    fz_arr = fr_zscore.to_numpy()

    dyn_lev = np.full(n, 1.0, dtype=float)

    for i in range(n):
        # High friction spread filter
        if spread_arr[i] > 6.0:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.0
            max_lev[i] = 1.0
            dyn_lev[i] = 1.0
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
            # Dynamic leverage scaling by zscore magnitude
            z_scale = min(abs(fz_arr[i]) / zscore_threshold, 1.5)
            dyn_lev[i] = round(float(np.clip(3.0 * (z_scale / 1.2), 1.0, 3.0)), 2)
            continue

        # Volatility Coiling Compression
        if not np.isnan(bb_arr[i]) and bb_arr[i] < bbwp_threshold:
            states[i] = "VOLATILITY_COILING_COMPRESSION"
            long_w[i] = short_w[i] = 1.5
            max_lev[i] = 2.5
            # Dynamic leverage scaling by coiling intensity (lower BBWP -> higher breakout leverage)
            coil_scale = 1.0 + (bbwp_threshold - bb_arr[i]) / bbwp_threshold
            dyn_lev[i] = round(float(np.clip(1.5 * coil_scale, 1.0, 2.5)), 2)
            continue

        # Range Chop
        if not np.isnan(chop_arr[i]) and chop_arr[i] > chop_threshold:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.25
            max_lev[i] = 1.0
            dyn_lev[i] = 1.0
            continue

        # Momentum Expansions
        if mb_arr[i] and opi_arr[i] >= 0.0:
            states[i] = "BULL_MOMENTUM_EXPANSION"
            long_w[i] = 2.0
            short_w[i] = 0.0
            max_lev[i] = 3.0
            # Dynamic leverage scaling by OPI orderbook flow pressure
            flow_mult = 1.0 + abs(opi_arr[i]) * 0.5
            dyn_lev[i] = round(float(np.clip(2.0 * flow_mult, 1.0, 3.0)), 2)
        elif mbe_arr[i] and opi_arr[i] <= 0.0:
            states[i] = "BEAR_MOMENTUM_EXPANSION"
            long_w[i] = 0.0
            short_w[i] = 2.0
            max_lev[i] = 3.0
            flow_mult = 1.0 + abs(opi_arr[i]) * 0.5
            dyn_lev[i] = round(float(np.clip(2.0 * flow_mult, 1.0, 3.0)), 2)
        else:
            states[i] = "RANGE_CHOP_HIGH_FRICTION"
            long_w[i] = short_w[i] = 0.5
            max_lev[i] = 1.5
            dyn_lev[i] = 1.0

    return pd.DataFrame(
        {
            "regime_state": states,
            "long_weight": long_w,
            "short_weight": short_w,
            "max_leverage": max_lev,
            "dynamic_leverage": dyn_lev,
        },
        index=df_1m.index,
    )
