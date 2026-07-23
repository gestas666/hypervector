"""Phase 2 NautilusTrader integration (historical event sim).

Historical path loads VectorBT export params and re-runs strategy logic.
Paper/shadow dry-run is ``paper-run``; live venue submit is ``live-run``
(outside this package).
"""

from hypervector.nautilus.actor import (
    HypervectorStrategy,
    HypervectorStrategyConfig,
    config_from_loadout,
)
from hypervector.nautilus.config_stub import Phase2StubConfig, build_phase2_stub_config
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.runner import Phase2Result, run_phase2_backtest

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
