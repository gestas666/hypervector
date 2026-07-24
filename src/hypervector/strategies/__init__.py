"""Strategy registry and classic / crown-stack / trend-ride / pine-composite / apex baselines."""

from hypervector.strategies.classic import register_classic_baselines
from hypervector.strategies.crown_stack import register_crown_stack
from hypervector.strategies.funding_momentum import register_funding_momentum
from hypervector.strategies.oi_divergence import register_oi_divergence
from hypervector.strategies.pine_composite import register_pine_composite
from hypervector.strategies.registry import StrategySpec, get_strategy, list_strategies, register
from hypervector.strategies.trend_ride import register_trend_ride


def register_all_strategies() -> None:
    register_classic_baselines()
    register_crown_stack()
    register_trend_ride()
    register_pine_composite()
    register_oi_divergence()
    register_funding_momentum()
    import hypervector.strategies.impulse_1m


__all__ = [
    "StrategySpec",
    "get_strategy",
    "list_strategies",
    "register",
    "register_all_strategies",
    "register_classic_baselines",
    "register_crown_stack",
    "register_trend_ride",
    "register_pine_composite",
    "register_oi_divergence",
    "register_funding_momentum",
]
