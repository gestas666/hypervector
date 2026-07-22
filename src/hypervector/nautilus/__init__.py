"""Phase 2 NautilusTrader integration (load-export stub first).

Historical event sim loads VectorBT export params and re-runs strategy logic.
Paper/live modes are not implemented in this package surface yet.
"""

from hypervector.nautilus.config_stub import Phase2StubConfig, build_phase2_stub_config
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout

__all__ = [
    "Phase2StubConfig",
    "StrategyLoadout",
    "build_phase2_stub_config",
    "load_strategy_loadout",
]
