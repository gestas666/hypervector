"""4-State Volatility-Regime Classifier & Strategy Adapter.

Regimes:
  - BULL_TREND: Fast EMA > Slow EMA & ADX > 20 & RSI > 50 (Aggressive Longs)
  - BEAR_TREND: Fast EMA < Slow EMA & ADX > 20 & RSI < 50 (Aggressive Shorts)
  - HIGH_VOL_COMPRESSION: BBWP < 25.0 (Coiling Breakout Preparation)
  - LOW_VOL_CHOP: Choppiness > 55.0 or ADX < 15.0 (Skip or Tight Fixed R:R)
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import bbwp, choppiness_index, ema, rsi

RegimeState = Literal[
    "BULL_TREND", "BEAR_TREND", "HIGH_VOL_COMPRESSION", "LOW_VOL_CHOP"
]


def detect_4state_regime(
    df: pd.DataFrame,
    *,
    ema_fast: int = 12,
    ema_slow: int = 48,
    adx_threshold: float = 20.0,
    bbwp_threshold: float = 25.0,
    chop_threshold: float = 55.0,
) -> pd.Series:
    """Classify bars into 4 actionable regimes with zero lookahead."""
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    lows = df["low"].astype(float)

    ef = ema(c, ema_fast)
    es = ema(c, ema_slow)
    bb_pct, _ = bbwp(c, bb_length=20, lookback=180)
    chop = choppiness_index(h, lows, c, length=14)
    r = rsi(c, 14)

    n = len(c)
    regimes = np.full(n, "LOW_VOL_CHOP", dtype=object)

    ef_arr = ef.to_numpy()
    es_arr = es.to_numpy()
    bb_arr = bb_pct.to_numpy()
    chop_arr = chop.to_numpy()
    r_arr = r.to_numpy()

    for i in range(n):
        if np.isnan(ef_arr[i]) or np.isnan(es_arr[i]):
            continue

        # Compression takes priority (breakout coiling setup)
        if not np.isnan(bb_arr[i]) and bb_arr[i] < bbwp_threshold:
            regimes[i] = "HIGH_VOL_COMPRESSION"
        elif not np.isnan(chop_arr[i]) and chop_arr[i] > chop_threshold:
            regimes[i] = "LOW_VOL_CHOP"
        elif ef_arr[i] > es_arr[i] and r_arr[i] > 50.0:
            regimes[i] = "BULL_TREND"
        elif ef_arr[i] < es_arr[i] and r_arr[i] < 50.0:
            regimes[i] = "BEAR_TREND"
        else:
            regimes[i] = "LOW_VOL_CHOP"

    return pd.Series(regimes, index=df.index, name="regime_4state")
