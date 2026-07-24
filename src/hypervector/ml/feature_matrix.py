"""Vectorized metalabel feature matrix (matches impulse BTC 1m schema).

Feature names are stable for the installed LightGBM bundle. PIT: each row uses
only information available at that bar close (no future peek).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import atr, ema, rsi

# Stable schema — keep in sync with data/models/metalabel/metalabel_metadata.json
FEATURE_NAMES: list[str] = [
    "close_vs_ema21_bps",
    "di_delta_1m",
    "roc_5_pct",
    "rsi_1m",
    "adx_1m",
    "plus_di_1m",
    "minus_di_1m",
    "realized_vol_24",
    "atr_14_pct",
    "bb_position_20",
    "gap_from_low_30_pct",
    "gap_from_high_30_pct",
    "consecutive_red_bars",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


def _wilder_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    length: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (+DI, -DI, ADX) Wilder-smoothed."""
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    up = h.diff()
    down = -l.diff()
    plus_dm = up.where((up > down) & (up > 0.0), 0.0)
    minus_dm = down.where((down > up) & (down > 0.0), 0.0)
    tr = pd.concat(
        [(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    alpha = 1.0 / float(length)
    atr_w = tr.ewm(alpha=alpha, min_periods=length, adjust=False).mean()
    plus_sm = plus_dm.ewm(alpha=alpha, min_periods=length, adjust=False).mean()
    minus_sm = minus_dm.ewm(alpha=alpha, min_periods=length, adjust=False).mean()
    plus_di = 100.0 * plus_sm / atr_w.replace(0.0, np.nan)
    minus_di = 100.0 * minus_sm / atr_w.replace(0.0, np.nan)
    dx = (
        100.0
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0.0, np.nan)
    )
    adx = dx.ewm(alpha=alpha, min_periods=length, adjust=False).mean()
    return plus_di.fillna(20.0), minus_di.fillna(20.0), adx.fillna(20.0)


def _consecutive_red(open_: pd.Series, close: pd.Series) -> pd.Series:
    o = open_.astype(float).to_numpy()
    c = close.astype(float).to_numpy()
    n = len(c)
    out = np.zeros(n, dtype=float)
    run = 0
    for i in range(n):
        if c[i] < o[i]:
            run += 1
        else:
            run = 0
        out[i] = float(run)
    return pd.Series(out, index=close.index)


BOOK_FEATURE_NAMES: list[str] = [
    "spread_bps",
    "obi_5",
    "obi_10",
    "book_depth_ratio",
    "micro_price_delta_bps",
    "book_pressure",
]


def build_feature_matrix(df: pd.DataFrame, include_book: bool = True) -> pd.DataFrame:
    """Build one feature row per bar. Requires open/high/low/close (+ timestamp optional)."""
    need = {"open", "high", "low", "close"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV missing columns: {sorted(missing)}")

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    ema21 = ema(c, 21)
    close_vs_ema21_bps = (c - ema21) / ema21.replace(0.0, np.nan) * 10_000.0
    plus_di, minus_di, adx = _wilder_dmi(h, l, c, 14)
    roc_5 = c.pct_change(5) * 100.0
    r = rsi(c, 14)
    log_ret = np.log(c / c.shift(1))
    realized_vol_24 = log_ret.rolling(24, min_periods=12).std() * math.sqrt(525_600)
    atr14 = atr(h, l, c, 14)
    atr_14_pct = atr14 / c.replace(0.0, np.nan) * 100.0
    mid = c.rolling(20, min_periods=10).mean()
    std = c.rolling(20, min_periods=10).std()
    upper = mid + 2.0 * std
    lower = mid - 2.0 * std
    bb_position_20 = ((c - lower) / (upper - lower).replace(0.0, np.nan)).clip(0.0, 1.0)
    gap_from_low_30_pct = (
        (c - l.rolling(30, min_periods=10).min())
        / l.rolling(30, min_periods=10).min().replace(0.0, np.nan)
        * 100.0
    )
    gap_from_high_30_pct = (
        (c - h.rolling(30, min_periods=10).max())
        / h.rolling(30, min_periods=10).max().replace(0.0, np.nan)
        * 100.0
    )
    consecutive_red_bars = _consecutive_red(o, c)

    # Time features from timestamp column or index
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        ts = pd.DatetimeIndex(df.index)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
    else:
        # Synthetic 1m clock from bar index (still cyclic structure)
        ts = pd.to_datetime(
            pd.Series(np.arange(len(df)), index=df.index) * 60_000,
            unit="ms",
            utc=True,
        )

    if not isinstance(ts, pd.Series):
        ts = pd.Series(ts, index=df.index)

    hour = ts.dt.hour.astype(float) + ts.dt.minute.astype(float) / 60.0
    dow = ts.dt.dayofweek.astype(float)
    hour_sin = np.sin(2 * math.pi * hour / 24.0)
    hour_cos = np.cos(2 * math.pi * hour / 24.0)
    dow_sin = np.sin(2 * math.pi * dow / 7.0)
    dow_cos = np.cos(2 * math.pi * dow / 7.0)

    feature_cols = {
        "close_vs_ema21_bps": close_vs_ema21_bps,
        "di_delta_1m": plus_di - minus_di,
        "roc_5_pct": roc_5,
        "rsi_1m": r,
        "adx_1m": adx,
        "plus_di_1m": plus_di,
        "minus_di_1m": minus_di,
        "realized_vol_24": realized_vol_24,
        "atr_14_pct": atr_14_pct,
        "bb_position_20": bb_position_20.fillna(0.5),
        "gap_from_low_30_pct": gap_from_low_30_pct,
        "gap_from_high_30_pct": gap_from_high_30_pct,
        "consecutive_red_bars": consecutive_red_bars,
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "dow_sin": dow_sin,
        "dow_cos": dow_cos,
    }

    # Add Orderbook features if present in df
    book_cols_to_use = []
    if include_book:
        for bcol in BOOK_FEATURE_NAMES:
            if bcol in df.columns:
                feature_cols[bcol] = df[bcol].astype(float)
                book_cols_to_use.append(bcol)

    out = pd.DataFrame(feature_cols, index=df.index)

    # Fill residual NaNs for early bars
    defaults = {
        "close_vs_ema21_bps": 0.0,
        "di_delta_1m": 0.0,
        "roc_5_pct": 0.0,
        "rsi_1m": 50.0,
        "adx_1m": 20.0,
        "plus_di_1m": 20.0,
        "minus_di_1m": 20.0,
        "realized_vol_24": 0.0,
        "atr_14_pct": 0.1,
        "bb_position_20": 0.5,
        "gap_from_low_30_pct": 0.0,
        "gap_from_high_30_pct": 0.0,
        "consecutive_red_bars": 0.0,
        "spread_bps": 1.5,
        "obi_5": 0.0,
        "obi_10": 0.0,
        "book_depth_ratio": 1.0,
        "micro_price_delta_bps": 0.0,
        "book_pressure": 0.0,
    }
    for col, d in defaults.items():
        if col in out.columns:
            out[col] = out[col].fillna(d)

    cols_order = list(FEATURE_NAMES) + [c for c in book_cols_to_use if c not in FEATURE_NAMES]
    return out[cols_order]

