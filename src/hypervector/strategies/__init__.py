"""Strategy registry and the place where strategy families are registered.

A strategy family is a module that defines its signal builders and a
``register_family()`` function calling
:func:`hypervector.strategies.registry.register` once per
:class:`~hypervector.strategies.registry.StrategySpec` (each spec declares
its :class:`~hypervector.strategies.registry.ExecutionProfile`). To make a
family available to every command (backtest, sweep, tune, pipeline,
Nautilus, paper, live), add its dotted module path to
:data:`STRATEGY_FAMILY_MODULES`. No family is built in.
"""

from importlib import import_module

#: Dotted paths of the strategy family modules :func:`register_all_strategies`
#: imports; each must define ``register_family()``. This is the one place a
#: new family is added.
STRATEGY_FAMILY_MODULES: tuple[str, ...] = ()

_EXPORTS = {
    "ExecutionProfile": ("hypervector.strategies.registry", "ExecutionProfile"),
    "StrategySpec": ("hypervector.strategies.registry", "StrategySpec"),
    "execution_profile": ("hypervector.strategies.registry", "execution_profile"),
    "get_strategy": ("hypervector.strategies.registry", "get_strategy"),
    "list_strategies": ("hypervector.strategies.registry", "list_strategies"),
    "register": ("hypervector.strategies.registry", "register"),
}

__all__ = [
    "ExecutionProfile",
    "STRATEGY_FAMILY_MODULES",
    "StrategySpec",
    "execution_profile",
    "get_strategy",
    "list_strategies",
    "register",
    "register_all_strategies",
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
    """Register every family listed in :data:`STRATEGY_FAMILY_MODULES`.

    Idempotent: a family re-registers its specs by name. Specs registered
    directly with ``register()`` stay registered.
    """
    for module_path in STRATEGY_FAMILY_MODULES:
        module = import_module(module_path)
        register_family = getattr(module, "register_family", None)
        if not callable(register_family):
            raise TypeError(
                f"strategy family module {module_path} must define register_family()"
            )
        register_family()
