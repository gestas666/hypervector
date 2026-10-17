"""Crown stack on chart TF (MVP 1m): EMA bias + Crown EMAs + BBWP + RSI + PMARP.

All lengths are bar counts on the series timeframe (1m for Phase 1 MVP),
not calendar days.

Roles:
  - Dominant trend: 21/55 EMA bias on 1m (block counter-trend)
  - Execution: 9/21/55 EMA crown stack on 1m
  - BBWP: enter only in compression (< threshold percentile)
  - RSI(14) vs EMA(7): continuation momentum
  - PMARP: mean-reversion / extreme profit-taking exits
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from hypervector.regime.detectors import detect_regime_ema
from hypervector.strategies.indicators import (
    bbwp,
    crown_emas,
    ema,
    ema_bias,
    pmarp,
    rsi,
)
from hypervector.strategies.registry import StrategySpec, register


def _stack_signals(
    df: pd.DataFrame,
    *,
    direction: str,
    bias_fast: int = 21,
    bias_slow: int = 55,
    crown_fast: int = 9,
    crown_mid: int = 21,
    crown_slow: int = 55,
    bbwp_lookback: int = 100,
    bbwp_threshold: float = 25.0,
    bb_length: int = 20,
    bbwp_signal: int = 5,
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
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    if direction not in ("long", "short"):
        raise ValueError("direction must be long|short")
    close = df["close"].astype(float)
    # Chart-TF bias (1m bars): 21/55 minute EMAs, not daily
    bias = ema_bias(close, fast=bias_fast, slow=bias_slow)
    e9, e21, e55 = crown_emas(close, crown_fast, crown_mid, crown_slow)
    bb_pct, bb_sig = bbwp(
        close, bb_length=bb_length, lookback=bbwp_lookback, signal_sma=bbwp_signal
    )
    compression = bb_sig.fillna(bb_pct) < bbwp_threshold

    r = rsi(close, rsi_length)
    r_sig = ema(r, rsi_signal)
    pm = pmarp(close, ema_length=pmarp_ema, lookback=pmarp_lookback)

    bull_stack = (e9 > e21) & (e21 > e55)
    bear_stack = (e9 < e21) & (e21 < e55)
    cross_up = (e9 > e21) & (e9.shift(1) <= e21.shift(1))
    cross_dn = (e9 < e21) & (e9.shift(1) >= e21.shift(1))

    rsi_bull = r > r_sig
    rsi_bear = r < r_sig

    bull_prev = bull_stack.shift(1).fillna(False).astype(bool)
    bear_prev = bear_stack.shift(1).fillna(False).astype(bool)

    if regime_filter:
        reg = detect_regime_ema(
            close,
            fast=int(regime_fast),
            slow=int(regime_slow),
            range_band=float(regime_band),
        )
        regime_long_ok = reg == "up"
        regime_short_ok = reg == "down"
    else:
        regime_long_ok = pd.Series(True, index=close.index)
        regime_short_ok = pd.Series(True, index=close.index)

    if direction == "long":
        macro = bias == 1
        stack_turn_up = bull_stack & (~bull_prev)
        entries = (
            macro.astype(bool)
            & regime_long_ok.fillna(False).astype(bool)
            & compression.fillna(False).astype(bool)
            & bull_stack.astype(bool)
            & (cross_up.fillna(False) | stack_turn_up)
            & rsi_bull.astype(bool)
        )
        exits = (
            cross_dn.fillna(False)
            | (pm >= pmarp_exit_hi).fillna(False)
            | (rsi_bear & (r < 50)).fillna(False)
            | (bias != 1)
            | (~regime_long_ok).fillna(False)
        )
    else:
        macro = bias == -1
        stack_turn_dn = bear_stack & (~bear_prev)
        entries = (
            macro.astype(bool)
            & regime_short_ok.fillna(False).astype(bool)
            & compression.fillna(False).astype(bool)
            & bear_stack.astype(bool)
            & (cross_dn.fillna(False) | stack_turn_dn)
            & rsi_bear.astype(bool)
        )
        exits = (
            cross_up.fillna(False)
            | (pm <= pmarp_exit_lo).fillna(False)
            | (rsi_bull & (r > 50)).fillna(False)
            | (bias != -1)
            | (~regime_short_ok).fillna(False)
        )

    # Optional Orderbook Gate
    book_gate = kwargs.get("book_gate", False)
    if book_gate:
        from hypervector.data.book_align import gate_signals_by_orderbook

        entries = gate_signals_by_orderbook(
            entries,
            df,
            direction=direction,
            max_spread_bps=float(kwargs.get("max_spread_bps", 8.0)),
            min_obi=float(kwargs.get("min_obi", -0.3)),
        )

    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool) & (~entries)
    return entries, exits, direction


def crown_stack_long(
    df: pd.DataFrame,
    bias_fast: int = 21,
    bias_slow: int = 55,
    crown_fast: int = 9,
    crown_mid: int = 21,
    crown_slow: int = 55,
    bbwp_lookback: int = 100,
    bbwp_threshold: float = 25.0,
    bb_length: int = 20,
    bbwp_signal: int = 5,
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
    # accept old kw names so prior grids/exports don't break
    daily_fast: int | None = None,
    daily_slow: int | None = None,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    if daily_fast is not None:
        bias_fast = daily_fast
    if daily_slow is not None:
        bias_slow = daily_slow
    return _stack_signals(
        df,
        direction="long",
        bias_fast=bias_fast,
        bias_slow=bias_slow,
        crown_fast=crown_fast,
        crown_mid=crown_mid,
        crown_slow=crown_slow,
        bbwp_lookback=bbwp_lookback,
        bbwp_threshold=bbwp_threshold,
        bb_length=bb_length,
        bbwp_signal=bbwp_signal,
        rsi_length=rsi_length,
        rsi_signal=rsi_signal,
        pmarp_lookback=pmarp_lookback,
        pmarp_ema=pmarp_ema,
        pmarp_exit_hi=pmarp_exit_hi,
        pmarp_exit_lo=pmarp_exit_lo,
        regime_filter=regime_filter,
        regime_fast=regime_fast,
        regime_slow=regime_slow,
        regime_band=regime_band,
        **kwargs,
    )


def crown_stack_short(
    df: pd.DataFrame,
    bias_fast: int = 21,
    bias_slow: int = 55,
    crown_fast: int = 9,
    crown_mid: int = 21,
    crown_slow: int = 55,
    bbwp_lookback: int = 100,
    bbwp_threshold: float = 25.0,
    bb_length: int = 20,
    bbwp_signal: int = 5,
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
    daily_fast: int | None = None,
    daily_slow: int | None = None,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    if daily_fast is not None:
        bias_fast = daily_fast
    if daily_slow is not None:
        bias_slow = daily_slow
    return _stack_signals(
        df,
        direction="short",
        bias_fast=bias_fast,
        bias_slow=bias_slow,
        crown_fast=crown_fast,
        crown_mid=crown_mid,
        crown_slow=crown_slow,
        bbwp_lookback=bbwp_lookback,
        bbwp_threshold=bbwp_threshold,
        bb_length=bb_length,
        bbwp_signal=bbwp_signal,
        rsi_length=rsi_length,
        rsi_signal=rsi_signal,
        pmarp_lookback=pmarp_lookback,
        pmarp_ema=pmarp_ema,
        pmarp_exit_hi=pmarp_exit_hi,
        pmarp_exit_lo=pmarp_exit_lo,
        regime_filter=regime_filter,
        regime_fast=regime_fast,
        regime_slow=regime_slow,
        regime_band=regime_band,
        **kwargs,
    )


def register_crown_stack() -> None:
    register(
        StrategySpec(
            name="crown_stack_long",
            role="uptrend",
            # BBWP + PMARP exit + optional EMA-regime gate
            param_grid={
                "bbwp_lookback": [100, 180, 252],
                "bbwp_threshold": [15.0, 20.0, 25.0],
                "pmarp_exit_hi": [85.0, 90.0, 95.0],
                "regime_filter": [True, False],
            },
            build_signals=crown_stack_long,
            description="1m EMA21/55 bias + Crown 9/21/55 + BBWP + RSI + PMARP (long)",
            supports_book_gate=True,
        )
    )
    register(
        StrategySpec(
            name="crown_stack_short",
            role="downtrend",
            param_grid={
                "bbwp_lookback": [100, 180, 252],
                "bbwp_threshold": [15.0, 20.0, 25.0],
                "pmarp_exit_lo": [10.0, 15.0],
            },
            build_signals=crown_stack_short,
            description="1m EMA21/55 bias + Crown 9/21/55 + BBWP + RSI + PMARP (short)",
            supports_book_gate=True,
        )
    )
