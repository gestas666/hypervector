"""Completed-bar exit decisions for low-timeframe replay variants."""

from __future__ import annotations

import pandas as pd

from hypervector.research.low_tf_multi_asset_replay_models import LowTfExitReason
from hypervector.research.shared_portfolio_models import Direction


def dynamic_low_tf_exit(
    *,
    variant: str,
    direction: Direction,
    stop_price: float,
    row: pd.Series,
    prior: pd.Series | None,
) -> LowTfExitReason | None:
    """Return a causal close-known exit or preserve the open position."""
    long = direction == "long"
    if variant == "range_close_invalidation":
        invalid = (
            float(row["close"]) < stop_price
            if long
            else float(row["close"]) > stop_price
        )
        return "close_invalidation" if invalid else None
    if variant == "rsi_reversal_exit":
        return _rsi_exit(long, row, prior)
    if variant == "ema_alignment_exit":
        invalid = (
            float(row["ema_fast_5m"]) <= float(row["ema_slow_5m"])
            if long
            else float(row["ema_fast_5m"]) >= float(row["ema_slow_5m"])
        )
        return "ema_alignment" if invalid else None
    if variant == "pmarp_opposite_extreme_exit":
        return _pmarp_exit(long, row)
    if variant in {"krown_close_stop_pmarp80", "krown_hard_stop_pmarp80"}:
        if float(row["pmarp"]) >= 80.0:
            return "pmarp_opposite_extreme"
        if variant == "krown_close_stop_pmarp80" and float(row["close"]) < stop_price:
            return "close_invalidation"
    if variant in {
        "krown_touch_close_stop_rsi_div",
        "krown_touch_hard_stop_rsi_div",
    }:
        if variant == "krown_touch_close_stop_rsi_div":
            invalid = (
                float(row["close"]) < stop_price
                if long
                else float(row["close"]) > stop_price
            )
            if invalid:
                return "close_invalidation"
        opposing = (
            bool(row["rsi_bearish_divergence"])
            if long
            else bool(row["rsi_bullish_divergence"])
        )
        return "rsi_divergence" if opposing else None
    return None


def _rsi_exit(
    long: bool, row: pd.Series, prior: pd.Series | None
) -> LowTfExitReason | None:
    if prior is None:
        return None
    current_gap = float(row["rsi"]) - float(row["rsi_signal"])
    prior_gap = float(prior["rsi"]) - float(prior["rsi_signal"])
    invalid = current_gap < 0.0 <= prior_gap if long else current_gap > 0.0 >= prior_gap
    return "rsi_reversal" if invalid else None


def _pmarp_exit(long: bool, row: pd.Series) -> LowTfExitReason | None:
    invalid = float(row["pmarp"]) >= 80.0 if long else float(row["pmarp"]) <= 20.0
    return "pmarp_opposite_extreme" if invalid else None
