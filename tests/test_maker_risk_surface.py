"""Predeclared BTC maker risk-surface tests."""

from __future__ import annotations

from importlib import import_module
import importlib.util
from pathlib import Path


def _load_script() -> object:
    path = Path("scripts/hypervelocity_maker_risk_surface.py")
    spec = importlib.util.spec_from_file_location("maker_risk_surface_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("risk-surface script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_risk_surface_is_complete_and_keeps_faithful_control() -> None:
    """Every predeclared allocation/leverage pair remains in the report."""
    module = import_module("hypervector.research.maker_risk_surface")
    configs = module.risk_surface_candidate_configs(
        initial_equity=15_000.0,
        entry_eligibility_seconds=60.0,
        fill_rule="trade-through",
    )

    assert tuple(configs) == (
        "alloc50_lev10",
        "alloc50_lev20",
        "alloc50_lev30",
        "alloc50_lev40",
        "alloc70_lev10",
        "alloc70_lev20",
        "alloc70_lev30",
        "alloc70_lev40_control",
        "alloc100_lev10",
        "alloc100_lev20",
        "alloc100_lev30",
        "alloc100_lev40",
    )
    assert all(config.initial_equity == 15_000.0 for config in configs.values())
    assert all(config.target_margin_pct == 8.0 for config in configs.values())
    assert all(config.reentry_cooldown_seconds == 60.0 for config in configs.values())
    control = configs["alloc70_lev40_control"]
    assert control.margin_fraction == 0.70
    assert control.leverage == 40.0
    assert control.entry_ttl_seconds == 60.0
    assert control.fill_rule == "trade-through"


def test_selected_peak_grid_changes_only_frozen_peak_fields() -> None:
    """Peak comparison keeps sizing candidates and the faithful control explicit."""
    module = import_module("hypervector.research.maker_risk_surface")
    configs = module.selected_peak_candidate_configs(
        initial_equity=15_000.0,
        entry_eligibility_seconds=60.0,
        fill_rule="trade-through",
    )

    assert tuple(configs) == (
        "alloc50_lev30",
        "alloc50_lev30_peak7",
        "alloc70_lev30",
        "alloc70_lev30_peak7",
        "alloc70_lev40_control",
    )
    for allocation in (50, 70):
        base = configs[f"alloc{allocation}_lev30"]
        peak = configs[f"alloc{allocation}_lev30_peak7"]
        assert peak.margin_fraction == base.margin_fraction
        assert peak.leverage == base.leverage == 30.0
        assert peak.peak_protection_activation_margin_pct == 7.0
        assert peak.peak_protection_lock_ratio == 0.55
        assert base.peak_protection_activation_margin_pct is None
    assert configs["alloc70_lev40_control"].leverage == 40.0


def test_selected_sizing_grid_keeps_only_30x_candidates_and_control() -> None:
    """The entry-contract discriminator avoids replaying rejected risk pairs."""
    module = import_module("hypervector.research.maker_risk_surface")
    configs = module.selected_sizing_candidate_configs(
        initial_equity=15_000.0,
        entry_eligibility_seconds=60.0,
        fill_rule="trade-through",
    )

    assert tuple(configs) == (
        "alloc50_lev30",
        "alloc70_lev30",
        "alloc70_lev40_control",
    )
    assert configs["alloc50_lev30"].margin_fraction == 0.50
    assert configs["alloc70_lev30"].leverage == 30.0
    assert configs["alloc70_lev40_control"].leverage == 40.0


def test_risk_surface_script_contract_is_report_only() -> None:
    """The surface command records every result without runtime authority."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "development-prices.parquet",
            "--development-funding-context",
            "development-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--out",
            "surface.json",
        ]
    )
    contract = module._experiment_contract(args)

    assert args.initial_equity == 15_000.0
    assert contract["candidate_family"] == "btc_allocation_leverage_surface_v1"
    assert contract["allocation_fractions"] == [0.5, 0.7, 1.0]
    assert contract["leverages"] == [10.0, 20.0, 30.0, 40.0]
    assert contract["runtime_strategy_changed"] is False
    assert contract["selection_is_promotion"] is False
    assert contract["model_authority"] == "observe"


def test_risk_surface_script_declares_selected_peak_mode() -> None:
    """The selected peak run is a separate frozen report-only family."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "development-prices.parquet",
            "--development-funding-context",
            "development-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--surface-mode",
            "selected-peak",
            "--out",
            "selected-peak.json",
        ]
    )
    contract = module._experiment_contract(args)

    assert contract["candidate_family"] == "btc_selected_peak_surface_v1"
    assert contract["peak_protection"] == {
        "activation_margin_pct": 7.0,
        "lock_ratio": 0.55,
    }
    assert contract["selection_is_promotion"] is False


def test_risk_surface_script_declares_24h_selected_sizing_contract() -> None:
    """The all-day source test records both the entry and sizing contracts."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "development-prices.parquet",
            "--development-funding-context",
            "development-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--entry-family",
            "source-follow-all-day-confidence-70",
            "--surface-mode",
            "selected-sizing",
            "--out",
            "all-day-sizing.json",
        ]
    )
    contract = module._experiment_contract(args)

    assert args.entry_family == "source-follow-all-day-confidence-70"
    assert contract["candidate_family"] == "btc_selected_sizing_surface_v1"
    assert contract["entry_family"] == "source-follow-all-day-confidence-70"
    assert contract["allocation_fractions"] == [0.5, 0.7]
    assert contract["leverages"] == [30.0, 40.0]
    assert contract["selection_is_promotion"] is False
