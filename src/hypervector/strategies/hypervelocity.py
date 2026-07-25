"""Hypervelocity 40x scalper — reverse-engineered external manual-position strategy.

Faithful implementation of the inferred rules in
``docs/external/reverse-engineering-plan--manual-position-strategy.md``
(sections 3, 4 and 7), derived from the empirical dataset
``docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.{md,json,csv}``:

  - Symbol: BTC/USDT perpetual, 40x constant leverage, maker fills
  - Trend-following momentum scalper: entries only with the prevailing trend
  - Entry: EMA(9/21) trend alignment + pullback to fast EMA + momentum
    confirmation + RSI extreme avoidance (+ optional EMA regime gate, Tier 1
    per plan section 7.3)
  - Exit: fixed margin target (~8% on margin == target/leverage price move),
    ATR-based stop, or trend-flip invalidation (plan section 4.5)
  - Observed: 36 closed positions, ~95.7% wins, exits clustered at +8% margin

Charter compliance (SRS_HV1_NO_GATES): every condition below is explicit,
user-configurable strategy logic. Nothing here aborts a trial; performance,
drawdown and trade counts remain reported results only.
Venue note (SRS_HV1_VENUE_SPEC): BTC venue max leverage is 40x — the default
``leverage`` matches the observed 40x and must not be raised above venue caps.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hypervector.regime.detectors import detect_regime_ema
from hypervector.strategies.indicators import atr as atr_indicator
from hypervector.strategies.indicators import ema, rsi
from hypervector.strategies.registry import StrategySpec, register


def _target_stop_exits(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    entries: pd.Series,
    *,
    direction: str,
    tp_frac: float,
    stop_dist: pd.Series,
) -> pd.Series:
    """Entry-anchored fixed-target / ATR-stop exits (plan section 4.5).

    On each entry bar the target price is ``entry * (1 +/- tp_frac)`` and the
    stop is ``entry -/+ atr_stop_mult * ATR(entry bar)``. Stop is evaluated
    before target on the same bar (conservative fill assumption).
    """
    n = len(close)
    c = close.to_numpy(dtype=float)
    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    e = entries.to_numpy(dtype=bool)
    sd = stop_dist.to_numpy(dtype=float)
    out = np.zeros(n, dtype=bool)

    in_pos = False
    tp_price = np.nan
    stop_price = np.nan
    for i in range(n):
        if not in_pos:
            if e[i]:
                in_pos = True
                entry_price = c[i]
                dist = sd[i] if not np.isnan(sd[i]) else entry_price * tp_frac * 0.5
                if direction == "long":
                    tp_price = entry_price * (1.0 + tp_frac)
                    stop_price = entry_price - dist
                else:
                    tp_price = entry_price * (1.0 - tp_frac)
                    stop_price = entry_price + dist
            continue
        if direction == "long":
            if l[i] <= stop_price or h[i] >= tp_price:
                out[i] = True
                in_pos = False
        else:
            if h[i] >= stop_price or l[i] <= tp_price:
                out[i] = True
                in_pos = False
    return pd.Series(out, index=close.index)


def build_hypervelocity_signals(
    df: pd.DataFrame,
    *,
    direction: str = "long",
    ema_fast: int = 9,
    ema_slow: int = 21,
    atr_period: int = 14,
    atr_stop_mult: float = 1.5,
    target_margin_pct: float = 8.0,
    leverage: float = 40.0,
    rsi_period: int = 14,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    momentum_lookback: int = 3,
    pullback_band_pct: float = 0.05,
    regime_filter: bool = True,
    regime_fast: int = 12,
    regime_slow: int = 48,
    regime_band: float = 0.001,
    **kwargs: Any,
) -> tuple[pd.Series, pd.Series, str]:
    """Reverse-engineered hypervelocity signals (plan sections 4.3-4.5).

    Entry (long): EMA(fast) > EMA(slow), pullback to fast EMA from above,
    momentum confirmation vs ``momentum_lookback`` bars ago, RSI below
    overbought, optional EMA regime gate. Short is the mirror image.

    Exit: fixed margin-return target (``target_margin_pct / leverage`` price
    move), ATR stop, or trend flip (fast/slow EMA cross against position).
    """
    if direction not in ("long", "short"):
        raise ValueError("direction must be long|short")

    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else close
    low = df["low"].astype(float) if "low" in df.columns else close

    ema_f = ema(close, ema_fast)
    ema_s = ema(close, ema_slow)
    r = rsi(close, rsi_period)
    a = atr_indicator(high, low, close, atr_period)

    # Required price move for the margin-return target at the given leverage
    # (e.g. 8% margin at 40x == 0.2% price move).
    tp_frac = (float(target_margin_pct) / max(float(leverage), 1.0)) / 100.0
    band = float(pullback_band_pct) / 100.0

    trend_up = ema_f > ema_s
    trend_down = ema_f < ema_s
    cross_dn = trend_down & trend_up.shift(1).fillna(False).astype(bool)
    cross_up = trend_up & trend_down.shift(1).fillna(False).astype(bool)

    momentum_up = close > close.shift(momentum_lookback)
    momentum_down = close < close.shift(momentum_lookback)

    pullback_long = (low <= ema_f * (1.0 + band)) & (close >= ema_f)
    pullback_short = (high >= ema_f * (1.0 - band)) & (close <= ema_f)

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
            trend_up.fillna(False)
            & pullback_long.fillna(False)
            & momentum_up.fillna(False)
            & (r < rsi_overbought).fillna(False)
            & regime_long_ok.fillna(False).astype(bool)
        )
        trend_flip = cross_dn | (~regime_long_ok).fillna(False) if regime_filter else cross_dn
    else:
        entries = (
            trend_down.fillna(False)
            & pullback_short.fillna(False)
            & momentum_down.fillna(False)
            & (r > rsi_oversold).fillna(False)
            & regime_short_ok.fillna(False).astype(bool)
        )
        trend_flip = cross_up | (~regime_short_ok).fillna(False) if regime_filter else cross_up

    entries = entries.fillna(False).astype(bool)

    barrier_exits = _target_stop_exits(
        close,
        high,
        low,
        entries,
        direction=direction,
        tp_frac=tp_frac,
        stop_dist=(float(atr_stop_mult) * a),
    )
    exits = (barrier_exits | trend_flip.fillna(False)).astype(bool)

    # Optional orderbook gate (maker-fill quality), same pattern as crown_stack
    if kwargs.get("book_gate", False):
        from hypervector.data.book_align import gate_signals_by_orderbook

        entries = gate_signals_by_orderbook(
            entries,
            df,
            direction=direction,
            max_spread_bps=float(kwargs.get("max_spread_bps", 5.0)),
            min_obi=float(kwargs.get("min_obi", 0.0)),
        )

    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool) & (~entries)
    return entries, exits, direction


def hypervelocity_long(df: pd.DataFrame, **kwargs: Any) -> tuple[pd.Series, pd.Series, str]:
    return build_hypervelocity_signals(df, direction="long", **kwargs)


def hypervelocity_short(df: pd.DataFrame, **kwargs: Any) -> tuple[pd.Series, pd.Series, str]:
    return build_hypervelocity_signals(df, direction="short", **kwargs)


_PARAM_GRID: dict[str, list[Any]] = {
    "ema_fast": [9],
    "ema_slow": [21],
    "atr_period": [14],
    "atr_stop_mult": [1.5, 2.0],
    "target_margin_pct": [6.0, 8.0, 10.0, 12.0],
    "leverage": [20.0, 40.0],
    "momentum_lookback": [3, 5],
    "regime_filter": [True, False],
}


def register_hypervelocity() -> None:
    """Register reverse-engineered hypervelocity strategy specs."""
    register(
        StrategySpec(
            name="hypervelocity_1m_scalper",
            role="regime",
            description=(
                "Reverse-engineered BTC 40x momentum scalper "
                "(EMA 9/21 trend + pullback + momentum, +8% margin target, ATR stop)"
            ),
            build_signals=hypervelocity_long,
            param_grid=dict(_PARAM_GRID),
        )
    )

    register(
        StrategySpec(
            name="hypervelocity_1m_scalper_long",
            role="uptrend",
            description="Reverse-engineered 40x scalper, long side (+8% margin target)",
            build_signals=hypervelocity_long,
            param_grid=dict(_PARAM_GRID),
        )
    )

    register(
        StrategySpec(
            name="hypervelocity_1m_scalper_short",
            role="downtrend",
            description="Reverse-engineered 40x scalper, short side (+8% margin target)",
            build_signals=hypervelocity_short,
            param_grid=dict(_PARAM_GRID),
        )
    )
