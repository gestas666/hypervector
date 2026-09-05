"""Input validation for causal report-only HYPE exit replays."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)

_REQUIRED_COLUMNS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "entry_side",
        "state_5m",
        "structural_direction",
        "funding_rate",
    }
)


def validate_hype_exit_market(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    policy: HypeExitPolicy,
) -> None:
    """Reject incomplete, ambiguous, or noncausal replay inputs."""
    missing = sorted(_REQUIRED_COLUMNS.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE exit replay market missing columns: {missing}")
    _validate_optional_inputs(market, config, policy)
    if len(market) < 2 or not isinstance(market.index, pd.DatetimeIndex):
        raise ValueError("HYPE exit replay requires at least two datetime bars")
    if market.index.tz is None or not market.index.is_monotonic_increasing:
        raise ValueError("HYPE exit replay index must be ordered and timezone-aware")
    if market.index.has_duplicates:
        raise ValueError("HYPE exit replay index must be unique")
    numeric = market[["open", "high", "low", "close", "funding_rate"]].astype(float)
    if not numeric.map(math.isfinite).to_numpy().all():
        raise ValueError("HYPE exit replay market must be finite")
    if (numeric[["open", "high", "low", "close"]] <= 0.0).to_numpy().any():
        raise ValueError("HYPE exit replay prices must be positive")


def _validate_optional_inputs(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    policy: HypeExitPolicy,
) -> None:
    _validate_stop_anchor_column(market, config)
    if config.maximum_hold_policy == "extend_while_regime_supported":
        missing = sorted({"state_1m", "context_15m"}.difference(market.columns))
        if missing:
            raise ValueError(f"HYPE extension market missing columns: {missing}")
    if policy.exit_on_5m_rsi_reversal:
        missing = sorted(
            {"regime_5m_rsi", "regime_5m_rsi_ema"}.difference(market.columns)
        )
        if missing:
            raise ValueError(f"HYPE momentum exit market missing columns: {missing}")


def _validate_stop_anchor_column(
    market: pd.DataFrame, config: HypeExitReplayConfig
) -> None:
    column = config.stop_anchor_column
    if column is None:
        return
    if column not in market:
        raise ValueError(f"HYPE stop anchor column is missing: {column}")
    selected = market.loc[market["entry_side"].isin(("long", "short")), column]
    numeric = pd.to_numeric(selected, errors="coerce")
    if numeric.isna().any() or not numeric.map(math.isfinite).all():
        raise ValueError("HYPE stop anchor values must be finite on entry signals")
    if numeric.le(0.0).any():
        raise ValueError("HYPE stop anchor values must be positive")
