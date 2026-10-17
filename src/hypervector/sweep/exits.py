"""Three TP/SL modes for research (fixed R:R, ATR, trail).

All distances are expressed as **fractions of entry price** for VectorBT
sl_stop / tp_stop. Trail is VectorBT's trailing ``sl_stop``: the distance is
fixed at entry (trail_atr_mult x ATR / close) and ratchets with the bar highs
(longs) or lows (shorts) of the open position, evaluated intrabar. There is
exactly one trailing stop per position and it resets with every new entry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import atr as atr_indicator

ExitModeName = Literal["fixed_rr", "atr", "trail"]
EXIT_MODES: tuple[str, ...] = ("fixed_rr", "atr", "trail")


@dataclass(frozen=True)
class ExitConfig:
    """TP/SL configuration — three modes."""

    mode: ExitModeName = "atr"
    # fixed_rr
    sl_pct: float = 0.01  # 1% stop
    rr: float = 2.0  # take profit = rr * sl distance
    # atr
    atr_length: int = 14
    sl_atr_mult: float = 1.5
    # trail
    trail_atr_mult: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_ohlc(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    if not {"high", "low", "close"}.issubset(df.columns):
        c = df["close"].astype(float)
        return c, c, c
    return df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)


def stop_distance_frac(
    df: pd.DataFrame,
    cfg: ExitConfig,
) -> pd.Series:
    """Per-bar stop distance as fraction of close (used for risk sizing + SL)."""
    high, low, close = _require_ohlc(df)
    if cfg.mode == "fixed_rr":
        return pd.Series(float(cfg.sl_pct), index=close.index)
    # atr or trail: base stop on ATR
    a = atr_indicator(high, low, close, cfg.atr_length)
    mult = cfg.sl_atr_mult if cfg.mode == "atr" else cfg.trail_atr_mult
    dist = (mult * a) / close.replace(0.0, np.nan)
    return dist.fillna(cfg.sl_pct).clip(lower=1e-6)


def tp_distance_frac(stop_frac: pd.Series, cfg: ExitConfig) -> pd.Series:
    """Take-profit distance as fraction of price (trail has no fixed TP)."""
    if cfg.mode == "trail":
        # no hard TP — use large RR as soft target only if needed; 0 disables tp_stop
        return pd.Series(np.nan, index=stop_frac.index)
    return (stop_frac * float(cfg.rr)).clip(lower=1e-6)


def apply_exit_mode(
    df: pd.DataFrame,
    entries: pd.Series,
    exits: pd.Series,
    *,
    direction: str,
    cfg: ExitConfig,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (entries, exits, sl_stop_frac, tp_stop_frac) for VectorBT.

    Strategy entries and exits pass through unchanged. Barrier exits are left
    to VectorBT: fixed_rr / atr use hard sl_stop + tp_stop, trail uses the
    trailing sl_stop (one stop per position, reset on every entry). The
    ``direction`` argument is accepted for API compatibility; distances are
    symmetric fractions of price.
    """
    del direction  # distances are direction-independent fractions
    entries = entries.reindex(df.index).fillna(False).astype(bool)
    exits = exits.reindex(df.index).fillna(False).astype(bool)
    stop_f = stop_distance_frac(df, cfg)
    tp_f = tp_distance_frac(stop_f, cfg)
    return entries, exits, stop_f, tp_f
