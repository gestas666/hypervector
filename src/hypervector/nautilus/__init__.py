"""Phase 2 NautilusTrader integration (historical event sim).

Historical path loads VectorBT export params and re-runs strategy logic.
Paper/shadow dry-run is ``paper-run``; live venue submit is ``live-run``
(outside this package).

Public names resolve lazily (PEP 562): importing a light helper such as
``hypervector.nautilus.hyperliquid_margin`` or ``load_export`` must not pull
in NautilusTrader (and its plotly tearsheet dependency). The engine loads
only when an engine-backed name below is first accessed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

_EXPORTS: dict[str, str] = {
    "HypervectorStrategy": "actor",
    "HypervectorStrategyConfig": "actor",
    "config_from_loadout": "actor",
    "Phase2StubConfig": "config_stub",
    "build_phase2_stub_config": "config_stub",
    "StrategyLoadout": "load_export",
    "load_strategy_loadout": "load_export",
    "Phase2Result": "runner",
    "run_phase2_backtest": "runner",
}

__all__ = [
    "HypervectorStrategy",
    "HypervectorStrategyConfig",
    "Phase2Result",
    "Phase2StubConfig",
    "StrategyLoadout",
    "build_phase2_stub_config",
    "config_from_loadout",
    "load_strategy_loadout",
    "run_phase2_backtest",
]
assert sorted(__all__) == sorted(_EXPORTS)

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from hypervector.nautilus.actor import (
        HypervectorStrategy,
        HypervectorStrategyConfig,
        config_from_loadout,
    )
    from hypervector.nautilus.config_stub import (
        Phase2StubConfig,
        build_phase2_stub_config,
    )
    from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
    from hypervector.nautilus.runner import Phase2Result, run_phase2_backtest


def __getattr__(name: str) -> Any:
    """Import the owning submodule on first access and cache the attribute."""
    submodule = _EXPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{submodule}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
