"""Name → builder + param schema + role (SRS_HV1_STRAT_MULTI)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import pandas as pd

Role = Literal["uptrend", "downtrend", "regime", "other"]
TradeDirection = Literal["long", "short"]

SignalBuilder = Callable[..., tuple[pd.Series, pd.Series, str]]


def normalize_direction(tag: str) -> TradeDirection:
    """Map a builder's direction tag ('long', 'impulse_1m_short', ...) to long|short.

    Strict: anything that is not exactly long/short or ``*_long``/``*_short``
    is a ValueError (no substring guessing).
    """
    text = str(tag).strip().lower() if isinstance(tag, str) else ""
    if text in ("long", "short"):
        return text  # type: ignore[return-value]
    if text.endswith("_long"):
        return "long"
    if text.endswith("_short"):
        return "short"
    raise ValueError(f"direction must be long|short, got {tag!r}")


@dataclass
class StrategySpec:
    name: str
    role: Role
    param_grid: dict[str, list[Any]]
    build_signals: SignalBuilder
    description: str = ""


_REGISTRY: dict[str, StrategySpec] = {}


def register(spec: StrategySpec) -> StrategySpec:
    _REGISTRY[spec.name] = spec
    return spec


def get_strategy(name: str) -> StrategySpec:
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy: {name}")
    return _REGISTRY[name]


def list_strategies(role: Role | None = None) -> list[StrategySpec]:
    specs = list(_REGISTRY.values())
    if role is not None:
        specs = [s for s in specs if s.role == role]
    return specs


def clear_registry() -> None:
    _REGISTRY.clear()
