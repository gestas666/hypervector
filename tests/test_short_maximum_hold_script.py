"""Contract tests for the source-following short maximum-hold experiment."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_script() -> object:
    path = Path("scripts/hypervelocity_short_maximum_hold.py")
    spec = importlib.util.spec_from_file_location("short_maximum_hold", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("short maximum-hold script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_maximum_hold_comparison_is_bounded_and_preserves_control() -> None:
    """Only the frozen 24h control and no-timeout candidate are replayed."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")

    assert tuple(configs) == ("max_hold_24h_control", "target_or_liquidation")
    assert configs["max_hold_24h_control"].maximum_hold_seconds == 86_400.0
    assert configs["target_or_liquidation"].maximum_hold_seconds is None
    assert all(config.margin_fraction == 0.35 for config in configs.values())
    assert all(config.leverage == 30.0 for config in configs.values())
    assert all(config.target_margin_pct == 8.0 for config in configs.values())


def test_maximum_hold_contract_has_no_runtime_or_model_authority() -> None:
    """The hold comparison cannot silently alter runtime or model authority."""
    module = _load_script()
    contract = module._contract(15_000.0, "trade-through")

    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["signal_changed"] is False
    assert contract["candidate_count"] == 2
    assert contract["candidate_difference"] == "maximum_hold_seconds_only"


def test_candidate_clears_the_per_signal_maximum_hold_override() -> None:
    """The no-timeout arm must not inherit the source row's 24h deadline."""
    module = _load_script()
    decisions = pd.DataFrame(
        {"entry_direction": ["short"], "maximum_hold_seconds": [86_400.0]},
        index=pd.DatetimeIndex(["2026-07-01T00:00:00Z"]),
    )

    grid = module._decision_grid(decisions)

    assert grid["max_hold_24h_control"] is decisions
    assert grid["max_hold_24h_control"]["maximum_hold_seconds"].iloc[0] == 86_400.0
    assert pd.isna(grid["target_or_liquidation"]["maximum_hold_seconds"].iloc[0])
    assert grid["target_or_liquidation"] is not decisions
