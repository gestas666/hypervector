"""Stop-price resolution shared by causal breakout exit replays."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.hype_breakout_exit_models import (
    HypeExitReplayConfig,
    HypeSide,
)


def resolve_replay_stop_price(
    market: pd.DataFrame,
    *,
    signal_position: int,
    entry_price: float,
    side: HypeSide,
    config: HypeExitReplayConfig,
) -> float:
    """Resolve a fixed or causally anchored stop from the actual entry fill."""
    column = config.stop_anchor_column
    if column is None:
        return _fixed_stop(entry_price, side, config.stop_bps)
    anchor = float(market[column].iloc[signal_position])
    if not math.isfinite(anchor) or anchor <= 0.0:
        raise ValueError("structural stop anchor must be positive and finite")
    signed_distance = entry_price - anchor if side == "long" else anchor - entry_price
    raw_bps = signed_distance / entry_price * 10_000.0
    minimum = _required(config.minimum_stop_bps)
    maximum = _required(config.maximum_stop_bps)
    return _fixed_stop(entry_price, side, min(maximum, max(minimum, raw_bps)))


def _fixed_stop(entry_price: float, side: HypeSide, distance_bps: float) -> float:
    fraction = distance_bps / 10_000.0
    return entry_price * (1.0 - fraction if side == "long" else 1.0 + fraction)


def _required(value: float | None) -> float:
    if value is None:
        raise RuntimeError("validated structural stop clamp is incomplete")
    return value
