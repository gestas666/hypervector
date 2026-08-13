"""Contract tests for independent liquidation-cooldown validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script() -> object:
    path = Path("scripts/hypervelocity_short_liquidation_cooldown_validation.py")
    spec = importlib.util.spec_from_file_location("short_cooldown_validation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("short cooldown-validation script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_replays_only_frozen_twenty_x_candidates() -> None:
    """Independent validation cannot expand the selected candidate surface."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")

    assert tuple(configs) == (
        "alloc35_lev20_control",
        "alloc35_lev20_lq_cd48h",
        "alloc35_lev20_lq_cd72h",
    )
    assert all(config.leverage == 20.0 for config in configs.values())
    assert all(config.margin_fraction == 0.35 for config in configs.values())


def test_validation_contract_is_report_only_and_frozen() -> None:
    """Independent validation has no runtime or model authority."""
    module = _load_script()
    contract = module._contract(15_000.0, "trade-through")

    assert contract["candidate_count"] == 3
    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["parameter_selection_allowed"] is False
