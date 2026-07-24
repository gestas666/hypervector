"""Pine Composite Strategy: Multi-indicator trend rider ported from Pine library.

Combines:
  1. Supertrend (supetrend.pine) - Macro trend direction filter & stop level
  2. ZLEMA (zero_lag_trend_signals.pine) - Pullback reclaim entries
  3. Squeeze Momentum (squeeze_momentum.pine) - Compression release & momentum filter
  4. Choppiness Index (choppines_indicator.pine) - Filter out sideways chop
  5. Vortex (vortex.pine) - VI+ vs VI- trend confirmation
  6. PMARP (crown_stack) - Extreme profit-taking exit
  7. Orderbook L2 Gating - Optional Microstructure filter (spread / OBI)
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


def pine_composite_signals(
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
    pmarp_exit_hi: float = 95.0,
    pmarp_exit_lo: float = 5.0,
    regime_filter: bool = True,
    regime_fast: int = 12,
    regime_slow: int = 48,
    regime_band: float = 0.001,
    book_gate: bool = False,
    max_spread_bps: float = 8.0,
    min_obi: float = -0.3,
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

    zl_reclaim_up = (
        (st_dir == 1)
        & (close > zlema)
        & (close.shift(1) <= zlema.shift(1))
    )
    zl_reclaim_dn = (
        (st_dir == -1)
        & (close < zlema)
        & (close.shift(1) >= zlema.shift(1))
    )

    if use_squeeze:
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
            | ((r > r_sig) & (r > 55)).fillna(False)
            | (~regime_short_ok).fillna(False)
        )

    # Optional Orderbook Gate
    if book_gate:
        from hypervector.data.book_align import gate_signals_by_orderbook
        entries = gate_signals_by_orderbook(
            entries,
            df,
            direction=direction,
            max_spread_bps=max_spread_bps,
            min_obi=min_obi,
        )

    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool) & (~entries)
    return entries, exits, direction


def pine_composite_long(df: pd.DataFrame, **kwargs) -> tuple[pd.Series, pd.Series, str]:
    return pine_composite_signals(df, direction="long", **kwargs)


def pine_composite_short(df: pd.DataFrame, **kwargs) -> tuple[pd.Series, pd.Series, str]:
    return pine_composite_signals(df, direction="short", **kwargs)


def register_pine_composite() -> None:
    register(
        StrategySpec(
            name="pine_composite_long",
            role="uptrend",
            param_grid={
                "st_atr": [10, 14],
                "st_mult": [2.5, 3.0, 3.5],
                "chop_max": [45.0, 50.0],
                "regime_filter": [True],
                "zl_length": [50, 70],
                "pmarp_exit_hi": [90.0, 95.0],
            },
            build_signals=pine_composite_long,
            description="Pine Composite: Supertrend+ZLEMA+Squeeze+Chop+Vortex+PMARP uptrend long",
        )
    )
    register(
        StrategySpec(
            name="pine_composite_short",
            role="downtrend",
            param_grid={
                "st_atr": [10, 14],
                "st_mult": [2.5, 3.0, 3.5],
                "chop_max": [45.0, 50.0],
                "regime_filter": [True],
                "zl_length": [50, 70],
                "pmarp_exit_lo": [5.0, 10.0],
            },
            build_signals=pine_composite_short,
            description="Pine Composite: Supertrend+ZLEMA+Squeeze+Chop+Vortex+PMARP downtrend short",
        )
    )
