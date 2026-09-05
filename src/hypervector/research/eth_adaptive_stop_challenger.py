"""Causal stop-anchor construction for the preregistered ETH challenger."""

from __future__ import annotations

import math

import pandas as pd

ANCHOR_COLUMN = "eth_adaptive_stop_anchor"
ATR_COLUMN = "eth_wilder_atr_14"
STRUCTURE_COLUMN = "eth_side_structure_12"
_PRICE_COLUMNS = ("open", "high", "low", "close")


def build_eth_adaptive_stop_market(
    market: pd.DataFrame,
    *,
    atr_period: int = 14,
    structure_lookback: int = 12,
    atr_multiple: float = 1.5,
) -> pd.DataFrame:
    """Add causal ATR, side-specific structure, and entry stop anchors."""
    _validate_market(market)
    _validate_parameters(atr_period, structure_lookback, atr_multiple)
    result = market.copy()
    atr = _wilder_atr(result, atr_period)
    rolling_low = result["low"].rolling(structure_lookback).min()
    rolling_high = result["high"].rolling(structure_lookback).max()
    sides = result["entry_side"]
    structure = rolling_low.where(
        sides.eq("long"), rolling_high.where(sides.eq("short"))
    )
    long_anchor = pd.concat(
        (result["close"] - atr_multiple * atr, rolling_low), axis=1
    ).min(axis=1)
    short_anchor = pd.concat(
        (result["close"] + atr_multiple * atr, rolling_high), axis=1
    ).max(axis=1)
    anchor = long_anchor.where(sides.eq("long"), short_anchor.where(sides.eq("short")))
    _require_complete_signal_anchors(anchor, sides)
    result[ATR_COLUMN] = atr
    result[STRUCTURE_COLUMN] = structure
    result[ANCHOR_COLUMN] = anchor
    return result


def _wilder_atr(market: pd.DataFrame, period: int) -> pd.Series:
    previous_close = market["close"].shift(1)
    true_range = pd.concat(
        (
            market["high"] - market["low"],
            (market["high"] - previous_close).abs(),
            (market["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    return true_range.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def _validate_market(market: pd.DataFrame) -> None:
    missing = sorted(set((*_PRICE_COLUMNS, "entry_side")).difference(market.columns))
    if missing:
        raise ValueError(f"ETH adaptive-stop market missing columns: {missing}")
    if not isinstance(market.index, pd.DatetimeIndex) or market.index.tz is None:
        raise ValueError("ETH adaptive-stop market requires timezone-aware bars")
    if not market.index.is_monotonic_increasing or market.index.has_duplicates:
        raise ValueError("ETH adaptive-stop bars must be uniquely ordered")
    numeric = market[list(_PRICE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    if (
        numeric.isna().to_numpy().any()
        or not numeric.map(math.isfinite).to_numpy().all()
    ):
        raise ValueError("ETH adaptive-stop prices must be finite")
    if numeric.le(0.0).to_numpy().any():
        raise ValueError("ETH adaptive-stop prices must be positive")
    invalid_sides = set(market["entry_side"].dropna()).difference(
        {"", "neutral", "long", "short"}
    )
    if invalid_sides:
        raise ValueError(
            f"ETH adaptive-stop entry sides are invalid: {sorted(invalid_sides)}"
        )


def _validate_parameters(period: int, lookback: int, multiple: float) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("ATR period must be a positive integer")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise ValueError("structure lookback must be a positive integer")
    if not math.isfinite(multiple) or multiple <= 0.0:
        raise ValueError("ATR multiple must be positive and finite")


def _require_complete_signal_anchors(
    anchor: pd.Series,
    sides: pd.Series,
) -> None:
    signals = sides.isin(("long", "short"))
    if anchor.loc[signals].isna().any():
        raise ValueError("ETH adaptive-stop signal occurred before indicator warmup")
