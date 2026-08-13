"""Name → builder + param schema + role (SRS_HV1_STRAT_MULTI)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import pandas as pd

Role = Literal["uptrend", "downtrend", "regime", "other"]

SignalBuilder = Callable[..., tuple[pd.Series, pd.Series, str]]


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
