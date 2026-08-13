"""Frozen contract tests for measured Hypervelocity exposure research."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_script() -> object:
    path = Path("scripts/hypervelocity_short_risk_surface.py")
    spec = importlib.util.spec_from_file_location("measured_risk_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("measured risk script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_measured_candidates_keep_original_price_target() -> None:
    """Reduced leverage must not silently move the BTC target farther away."""
    from hypervector.research.measured_hypervelocity_risk import (
        measured_hypervelocity_candidate_configs,
    )

    configs = measured_hypervelocity_candidate_configs(
        initial_equity=15_000.0,
        fill_rule="trade-through",
    )

    assert tuple(configs) == (
        "alloc35_lev30_control",
        "alloc05_lev03_no_stop",
        "alloc05_lev03_stop60",
        "alloc10_lev05_no_stop",
        "alloc10_lev05_stop60",
    )
    price_targets = {
        config.target_margin_pct / 100.0 / config.leverage
        for config in configs.values()
    }
    assert len(price_targets) == 1
    assert price_targets.pop() == pytest.approx(8.0 / 30.0 / 100.0)


def test_measured_candidates_bound_challenger_exposure() -> None:
    """Challengers use much less leverage and isolated margin than control."""
    from hypervector.research.measured_hypervelocity_risk import (
        measured_hypervelocity_candidate_configs,
    )

    configs = measured_hypervelocity_candidate_configs(
        initial_equity=15_000.0,
        fill_rule="trade-through",
    )
    challengers = [
        config for name, config in configs.items() if name != "alloc35_lev30_control"
    ]

    assert max(config.leverage for config in challengers) == 5.0
    assert max(config.margin_fraction for config in challengers) == 0.10
    assert configs["alloc05_lev03_stop60"].fixed_margin_stop_pct == pytest.approx(1.8)
    assert configs["alloc10_lev05_stop60"].fixed_margin_stop_pct == pytest.approx(3.0)
    assert configs["alloc05_lev03_no_stop"].fixed_margin_stop_pct is None
    assert configs["alloc10_lev05_no_stop"].fixed_margin_stop_pct is None


def test_measured_surface_remains_report_only() -> None:
    """The measured matrix cannot alter runtime or model authority."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--research-database",
            "market.duckdb",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--control-artifact",
            "control.json",
            "--fill-rule",
            "trade-through",
            "--surface-mode",
            "measured",
            "--out",
            "measured.json",
        ]
    )
    contract = module._contract(15_000.0, "trade-through", args.surface_mode)

    assert contract["candidate"] == "source_follow_measured_exposure_v1"
    assert contract["candidate_count"] == 5
    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["signal_changed"] is False
