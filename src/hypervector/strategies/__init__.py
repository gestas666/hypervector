"""Strategy registry and classic / crown-stack / trend-ride baselines."""

from hypervector.strategies.classic import register_classic_baselines
from hypervector.strategies.crown_stack import register_crown_stack
from hypervector.strategies.registry import StrategySpec, get_strategy, list_strategies, register
from hypervector.strategies.trend_ride import register_trend_ride


def register_all_strategies() -> None:
    register_classic_baselines()
    register_crown_stack()
    register_trend_ride()


__all__ = [
    "StrategySpec",
    "get_strategy",
    "list_strategies",
    "register",
    "register_all_strategies",
    "register_classic_baselines",
    "register_crown_stack",
    "register_trend_ride",
]
