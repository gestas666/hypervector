"""Bar-window signal adapter: strategy registry → entry/exit for Nautilus actors.

Recomputes pure-Python signals from OHLCV windows. Does not reimplement
indicators — delegates to ``StrategySpec.build_signals`` from the registry.
Live alpha is always ``strategy_name`` + ``params`` (never signals.parquet).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pandas as pd

from hypervector.strategies import get_strategy, register_all_strategies
from hypervector.strategies.registry import SignalBuilder, StrategySpec

# Loadout / export metadata keys that never belong on a signal builder.
_META_PARAM_KEYS = frozenset({"strategy", "role", "exit_mode"})


@dataclass(frozen=True)
class SignalIntent:
    """Intent on a single bar for actor decisioning."""

    direction: str  # "long" | "short" | "flat"
    enter: bool
    exit: bool
    bar_index: int


@lru_cache(maxsize=256)
def _builder_kwarg_names(builder: SignalBuilder) -> frozenset[str] | None:
    """Accepted keyword names for ``builder`` (``None`` when it takes ``**kwargs``)."""
    sig = inspect.signature(builder)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return None
    return frozenset(
        name
        for name, p in sig.parameters.items()
        if name != "df"
        and p.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    )


def _filter_builder_params(
    builder: SignalBuilder,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Keep only kwargs the builder accepts (drop loadout metadata / extras)."""
    cleaned = {k: v for k, v in params.items() if k not in _META_PARAM_KEYS}
    try:
        allowed = _builder_kwarg_names(builder)
    except TypeError:  # unhashable callable: inspect directly
        allowed = _builder_kwarg_names.__wrapped__(builder)
    if allowed is None:
        return cleaned
    return {k: v for k, v in cleaned.items() if k in allowed}


def resolve_strategy_spec(strategy_name: str) -> StrategySpec:
    """Registered spec for ``strategy_name``; fills the registry only when needed."""
    try:
        return get_strategy(strategy_name)
    except KeyError:
        register_all_strategies()  # idempotent
        return get_strategy(strategy_name)


def signals_from_ohlcv(
    df: pd.DataFrame,
    strategy_name: str,
    params: dict[str, Any],
) -> tuple[pd.Series, pd.Series, str]:
    """Build entry/exit series for ``df`` via the registered strategy builder.

    Returns ``(entries, exits, direction)`` aligned to ``df`` index.
    """
    spec = resolve_strategy_spec(strategy_name)
    clean = _filter_builder_params(spec.build_signals, params)
    return spec.build_signals(df, **clean)


def last_bar_intent(
    df: pd.DataFrame,
    strategy_name: str,
    params: dict[str, Any],
) -> SignalIntent:
    """Signal intent on the final bar of the window."""
    entries, exits, direction = signals_from_ohlcv(df, strategy_name, params)
    i = len(df) - 1
    enter = bool(entries.iloc[i])
    exit_ = bool(exits.iloc[i])
    return SignalIntent(direction=direction, enter=enter, exit=exit_, bar_index=i)
