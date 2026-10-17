"""Lazy public exports for Hypervector strategies services."""

from importlib import import_module

_EXPORTS = {
    "register_classic_baselines": (
        "hypervector.strategies.classic",
        "register_classic_baselines",
    ),
    "register_crown_stack": (
        "hypervector.strategies.crown_stack",
        "register_crown_stack",
    ),
    "register_funding_momentum": (
        "hypervector.strategies.funding_momentum",
        "register_funding_momentum",
    ),
    "register_hypervelocity": (
        "hypervector.strategies.hypervelocity",
        "register_hypervelocity",
    ),
    "register_impulse_1m": ("hypervector.strategies.impulse_1m", "register_impulse_1m"),
    "register_oi_divergence": (
        "hypervector.strategies.oi_divergence",
        "register_oi_divergence",
    ),
    "register_pine_composite": (
        "hypervector.strategies.pine_composite",
        "register_pine_composite",
    ),
    "StrategySpec": ("hypervector.strategies.registry", "StrategySpec"),
    "get_strategy": ("hypervector.strategies.registry", "get_strategy"),
    "list_strategies": ("hypervector.strategies.registry", "list_strategies"),
    "register": ("hypervector.strategies.registry", "register"),
    "register_source_derived": (
        "hypervector.strategies.source_derived",
        "register_source_derived",
    ),
    "register_trend_ride": ("hypervector.strategies.trend_ride", "register_trend_ride"),
}

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
    "register_source_derived",
    "register_hypervelocity",
]


def __getattr__(name: str) -> object:
    """Resolve public services without importing unrelated execution engines."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value


def register_all_strategies() -> None:
    """Register every retained strategy family only when research needs it."""
    from hypervector.strategies.classic import register_classic_baselines
    from hypervector.strategies.crown_stack import register_crown_stack
    from hypervector.strategies.trend_ride import register_trend_ride
    from hypervector.strategies.pine_composite import register_pine_composite
    from hypervector.strategies.oi_divergence import register_oi_divergence
    from hypervector.strategies.funding_momentum import register_funding_momentum
    from hypervector.strategies.impulse_1m import register_impulse_1m
    from hypervector.strategies.source_derived import register_source_derived
    from hypervector.strategies.hypervelocity import register_hypervelocity

    register_classic_baselines()
    register_crown_stack()
    register_trend_ride()
    register_pine_composite()
    register_oi_divergence()
    register_funding_momentum()
    register_impulse_1m()
    register_source_derived()
    register_hypervelocity()
