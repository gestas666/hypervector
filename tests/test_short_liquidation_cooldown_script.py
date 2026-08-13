"""Contract tests for the post-liquidation short cooldown experiment."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script() -> object:
    path = Path("scripts/hypervelocity_short_liquidation_cooldown.py")
    spec = importlib.util.spec_from_file_location("short_liquidation_cooldown", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("short liquidation-cooldown script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cooldown_surface_is_bounded_and_preserves_controls() -> None:
    """Only the predeclared 48h/72h cooldown comparisons are replayed."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")

    assert tuple(configs) == (
        "alloc35_lev30_control",
        "alloc35_lev30_lq_cd48h",
        "alloc35_lev20_control",
        "alloc35_lev20_lq_cd48h",
        "alloc35_lev20_lq_cd72h",
    )
    assert configs["alloc35_lev30_control"].liquidation_reentry_cooldown_seconds == 0
    assert configs["alloc35_lev20_control"].liquidation_reentry_cooldown_seconds == 0
    assert (
        configs["alloc35_lev20_lq_cd48h"].liquidation_reentry_cooldown_seconds
        == 172_800.0
    )
    assert (
        configs["alloc35_lev20_lq_cd72h"].liquidation_reentry_cooldown_seconds
        == 259_200.0
    )


def test_cooldown_contract_has_no_runtime_or_model_authority() -> None:
    """The cooldown comparison remains report-only and ML-observe."""
    module = _load_script()
    contract = module._contract(15_000.0, "trade-through")

    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["signal_changed"] is False
    assert contract["candidate_count"] == 5
