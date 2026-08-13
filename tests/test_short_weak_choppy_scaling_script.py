"""Contract tests for the recent weak/choppy short sizing replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_short_weak_choppy_scaling.py")
    assert path.is_file(), "weak/choppy replay script is missing"
    spec = importlib.util.spec_from_file_location("weak_choppy_scaling", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("weak/choppy replay script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_weak_choppy_replay_is_report_only_and_preserves_risk() -> None:
    """Only the decision sizing annotation may differ from the exact control."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")
    contract = module._contract(15_000.0, "trade-through")

    assert tuple(configs) == ("uniform_control", "weak_choppy_half")
    assert configs["uniform_control"] == configs["weak_choppy_half"]
    assert configs["uniform_control"].margin_fraction == 0.35
    assert configs["uniform_control"].leverage == 30.0
    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["signal_changed"] is False
    assert contract["weak_choppy_allocation_multiplier"] == 0.5
