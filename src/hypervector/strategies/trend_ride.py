"""Frankenstein 1m trend-ride from pine library + crown pieces.

Pine sources (read-only ports, simplified to chart TF 1m):
  - supetrend.pine              → Supertrend direction (ride the trend)
  - zero_lag_trend_signals.pine → ZLEMA pullback entries in trend
  - squeeze_momentum.pine       → prefer release from squeeze with mom aligned
  - choppines_indicator.pine    → skip chop (CI high)
  - vortex.pine                 → VI+/VI- directional confirm
  - crown stack RSI/PMARP       → momentum filter + extreme exit

Long: ST up + not choppy + VI+ > VI- + (ST flip | ZLEMA reclaim in ST up)
      optional squeeze: mom > 0 when filter enabled
Short: mirror
"""

from __future__ import annotations

import pandas as pd

from hypervector.regime.detectors import detect_regime_ema
from hypervector.strategies.indicators import (
    choppiness_index,
    ema,
    pmarp,
    rsi,
    squeeze_momentum,
    supertrend,
    vortex,
    zero_lag_trend_ohlc,
)
from hypervector.strategies.registry import StrategySpec, register


def _ohlc(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    return df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)


def trend_ride_signals(
    df: pd.DataFrame,
    *,
    direction: str,
    st_atr: int = 10,
    st_mult: float = 3.0,
    zl_length: int = 70,
    zl_mult: float = 1.2,
    chop_length: int = 14,
    chop_max: float = 50.0,
    vortex_length: int = 14,
    use_squeeze: bool = True,
    sq_bb: int = 20,
    sq_kc: int = 20,
    rsi_length: int = 14,
    rsi_signal: int = 7,
    pmarp_lookback: int = 250,
    pmarp_ema: int = 21,
    pmarp_exit_hi: float = 90.0,
    pmarp_exit_lo: float = 10.0,
    regime_filter: bool = False,
    regime_fast: int = 12,
    regime_slow: int = 48,
    regime_band: float = 0.001,
) -> tuple[pd.Series, pd.Series, str]:
    if direction not in ("long", "short"):
        raise ValueError("direction must be long|short")
    high, low, close = _ohlc(df)

    st_line, st_dir = supertrend(high, low, close, atr_period=st_atr, multiplier=st_mult)
    zlema, zl_dir = zero_lag_trend_ohlc(high, low, close, length=zl_length, mult=zl_mult)
    chop = choppiness_index(high, low, close, chop_length)
    vip, vim = vortex(high, low, close, vortex_length)
    mom, sqz_on, sqz_off = squeeze_momentum(
        high, low, close, bb_length=sq_bb, kc_length=sq_kc
    )
    r = rsi(close, rsi_length)
    r_sig = ema(r, rsi_signal)
    pm = pmarp(close, ema_length=pmarp_ema, lookback=pmarp_lookback)

    trending = chop < chop_max
    st_flip_up = (st_dir == 1) & (st_dir.shift(1) == -1)
    st_flip_dn = (st_dir == -1) & (st_dir.shift(1) == 1)
    # pullback entry: in established ST trend, reclaim ZLEMA (zero_lag_trend_signals)
    zl_reclaim_up = (
        (st_dir == 1)
        & (zl_dir == 1)
        & (close > zlema)
        & (close.shift(1) <= zlema.shift(1))
    )
    zl_reclaim_dn = (
        (st_dir == -1)
        & (zl_dir == -1)
        & (close < zlema)
        & (close.shift(1) >= zlema.shift(1))
    )

    if use_squeeze:
        # allow entry during squeeze (coil) or right as it releases with mom
        sq_ok_long = sqz_on | (sqz_off & (mom > 0))
        sq_ok_short = sqz_on | (sqz_off & (mom < 0))
    else:
        sq_ok_long = pd.Series(True, index=close.index)
        sq_ok_short = pd.Series(True, index=close.index)

    if regime_filter:
        reg = detect_regime_ema(
            close, fast=int(regime_fast), slow=int(regime_slow), range_band=float(regime_band)
        )
        regime_long_ok = reg == "up"
        regime_short_ok = reg == "down"
    else:
        regime_long_ok = pd.Series(True, index=close.index)
        regime_short_ok = pd.Series(True, index=close.index)

    if direction == "long":
        entries = (
            trending.fillna(False)
            & regime_long_ok.fillna(False)
            & (st_dir == 1)
            & (vip > vim).fillna(False)
            & (r > r_sig).fillna(False)
            & sq_ok_long.fillna(False)
            & (st_flip_up.fillna(False) | zl_reclaim_up.fillna(False))
        )
        exits = (
            st_flip_dn.fillna(False)
            | (pm >= pmarp_exit_hi).fillna(False)
            | ((st_dir == -1) & (st_dir.shift(1) == 1)).fillna(False)
            | ((r < r_sig) & (r < 45)).fillna(False)
            | (~regime_long_ok).fillna(False)
        )
    else:
        entries = (
            trending.fillna(False)
            & regime_short_ok.fillna(False)
            & (st_dir == -1)
            & (vip < vim).fillna(False)
            & (r < r_sig).fillna(False)
            & sq_ok_short.fillna(False)
            & (st_flip_dn.fillna(False) | zl_reclaim_dn.fillna(False))
        )
        exits = (
            st_flip_up.fillna(False)
            | (pm <= pmarp_exit_lo).fillna(False)
            | ((st_dir == 1) & (st_dir.shift(1) == -1)).fillna(False)
            | ((r > r_sig) & (r > 55)).fillna(False)
            | (~regime_short_ok).fillna(False)
        )

    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool) & (~entries)
    return entries, exits, direction


def trend_ride_long(df: pd.DataFrame, **kwargs) -> tuple[pd.Series, pd.Series, str]:
    return trend_ride_signals(df, direction="long", **kwargs)


def trend_ride_short(df: pd.DataFrame, **kwargs) -> tuple[pd.Series, pd.Series, str]:
    return trend_ride_signals(df, direction="short", **kwargs)


def register_trend_ride() -> None:
    register(
        StrategySpec(
            name="trend_ride_long",
            role="uptrend",
            # Broader autotune: ST params + chop + squeeze + regime gate
            param_grid={
                "st_atr": [10, 14],
                "st_mult": [2.5, 3.0, 3.5, 4.0],
                "chop_max": [40.0, 45.0, 50.0],
                "use_squeeze": [True],
                "regime_filter": [True, False],
                "zl_length": [50, 70],
            },
            build_signals=trend_ride_long,
            description="Pine frankenstein: Supertrend+ZLEMA+Squeeze+Chop+Vortex+RSI/PMARP long",
        )
    )
    register(
        StrategySpec(
            name="trend_ride_short",
            role="downtrend",
            param_grid={
                "st_atr": [10, 14],
                "st_mult": [2.5, 3.0, 3.5, 4.0],
                "chop_max": [40.0, 45.0, 50.0],
                "use_squeeze": [True],
                "regime_filter": [True, False],
                "zl_length": [50, 70],
            },
            build_signals=trend_ride_short,
            description="Pine frankenstein: Supertrend+ZLEMA+Squeeze+Chop+Vortex+RSI/PMARP short",
        )
    )
