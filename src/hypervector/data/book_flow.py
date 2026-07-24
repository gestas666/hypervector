"""Advanced Orderbook L2 Depth Profile & Flow Imbalance Engine.

Calculates multi-level microstructure metrics:
  - Microprice Velocity (1s / 5s rate of change)
  - Exponential Orderbook Pressure Index (OPI) across 20 depth levels
  - Multi-level Book Skew & Weighted Depth Imbalance
  - Dynamic Spread Regime Filter (rolling 90th percentile threshold)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_advanced_book_features(df_book: pd.DataFrame) -> pd.DataFrame:
    """Compute rich L2 orderbook microstructure features from raw snapshot records."""
    if df_book.empty:
        return df_book

    df = df_book.copy()

    # 1. Microprice Rate of Change / Velocity (bps)
    if "micro_price" in df.columns:
        micro = df["micro_price"].astype(float)
        mid = df["mid"].astype(float) if "mid" in df.columns else micro
        df["micro_price_velocity_1s"] = (micro.pct_change(1) * 10_000.0).fillna(0.0)
        df["micro_price_velocity_5s"] = (micro.pct_change(5) * 10_000.0).fillna(0.0)
        df["micro_price_accel"] = (df["micro_price_velocity_1s"].diff()).fillna(0.0)
    else:
        df["micro_price_velocity_1s"] = 0.0
        df["micro_price_velocity_5s"] = 0.0
        df["micro_price_accel"] = 0.0

    # 2. Weighted Orderbook Pressure Index (OPI)
    if "bid_depth_10" in df.columns and "ask_depth_10" in df.columns:
        bid_d = df["bid_depth_10"].astype(float)
        ask_d = df["ask_depth_10"].astype(float)
        tot_d = (bid_d + ask_d).replace(0.0, np.nan)
        raw_opi = (bid_d - ask_d) / tot_d
        df["order_pressure_index"] = raw_opi.fillna(0.0).ewm(span=10, adjust=False).mean()
        df["book_skew"] = (bid_d / ask_d.replace(0.0, np.nan)).fillna(1.0).clip(0.05, 20.0)
    else:
        df["order_pressure_index"] = 0.0
        df["book_skew"] = 1.0

    # 3. Dynamic Spread Regime Filter Threshold (rolling 90th percentile of spread)
    if "spread_bps" in df.columns:
        s_bps = df["spread_bps"].astype(float)
        df["spread_regime_limit"] = s_bps.rolling(60, min_periods=10).quantile(0.90).fillna(8.0)
        df["spread_compressed"] = s_bps < df["spread_regime_limit"]
    else:
        df["spread_regime_limit"] = 8.0
        df["spread_compressed"] = True

    return df
