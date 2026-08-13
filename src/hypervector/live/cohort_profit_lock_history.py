"""Bounded completed-bar history requirements for configured profit locks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from hypervector.live.multi_asset_live_config import StrategyProviderConfig
from hypervector.live.multi_asset_market_bars import (
    CohortMarketBar,
    completed_market_bars,
)

_SECONDS_PER_MINUTE = 60
_BOUNDARY_BARS = 2


def profit_lock_history_limits(
    providers: Iterable[StrategyProviderConfig],
) -> dict[str, int]:
    """Return maximum lifecycle bar requirements for lock-enabled symbols."""
    limits: dict[str, int] = {}
    for provider in providers:
        contract = provider.execution
        symbols = _lock_enabled_symbols(provider)
        if not symbols:
            continue
        terminal = (
            contract.hard_maximum_hold_seconds
            if contract.maximum_hold_policy == "extend_while_regime_supported"
            else contract.maximum_hold_seconds
        )
        if terminal is None:
            raise ValueError("profit-lock provider lacks a terminal hold")
        bars = terminal // _SECONDS_PER_MINUTE + _BOUNDARY_BARS
        for symbol in symbols:
            limits[symbol] = max(limits.get(symbol, 0), bars)
    return limits


def _lock_enabled_symbols(provider: StrategyProviderConfig) -> set[str]:
    if provider.execution.profit_lock_policy != "none":
        return set(provider.symbols)
    return {
        override.symbol
        for override in provider.profit_lock_overrides
        if override.policy != "none"
    }


def profit_lock_market_bars(
    providers: Iterable[StrategyProviderConfig],
    bars: Mapping[tuple[str, str], pd.DataFrame],
    observed: pd.Timestamp,
) -> dict[str, tuple[CohortMarketBar, ...]]:
    """Project exact completed histories only for lock-enabled symbols."""
    return {
        symbol: completed_market_bars(
            bars[(symbol, "1m")], observed, symbol, limit=limit
        )
        for symbol, limit in profit_lock_history_limits(providers).items()
    }
