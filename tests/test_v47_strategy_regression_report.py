"""Acceptance tests for the v47 strategy-regression report."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "v47_strategy_regression_report.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("v47_strategy_regression_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_separates_defects_from_strategy_evidence() -> None:
    """Confirmed defects must not be mislabeled as negative edge."""
    module = _load_module()
    paths = module.default_report_paths(ROOT)

    artifact = module.build_report_artifact(paths)
    datasets = artifact["snapshot"]["datasets"]
    decisions = {row["strategy"]: row for row in datasets["strategy_decisions"]}

    assert decisions["HIP3 pressure v1"]["diagnosis"] == "confirmed contract defect"
    assert decisions["HIP3 pressure v1"]["affected_closed_trades"] == 4
    assert decisions["HIP3 pressure v1"]["affected_net_pnl_usd"] == -2.097088
    assert decisions["Range Onset"]["decision"] == "repair and retain"
    assert decisions["BTC sweep long"]["evidence"] == (
        "four resolved development wins, one resolved development loss, "
        "one unresolved apparent development win; one resolved forward win"
    )
    assert decisions["HT onset ETH/SOL"]["decision"] == "remove unchanged transfer"
    assert decisions["HIP3 Swing commodity"]["decision"] == "retire unchanged route"


def test_report_preserves_exact_candidate_risk_and_authority() -> None:
    """The report must preserve v47 identity, sizing, and inactive authority."""
    module = _load_module()
    artifact = module.build_report_artifact(module.default_report_paths(ROOT))
    datasets = artifact["snapshot"]["datasets"]
    capacity = datasets["candidate_capacity"][0]
    routes = datasets["candidate_routes"]

    assert (
        capacity["profile_id"] == "multi_asset_growth_first_5000_repaired_candidate_v47"
    )
    assert capacity["account_position_capacity"] == 10
    assert capacity["usable_asset_slots"] == 5
    assert capacity["leverage"] == 10.0
    assert capacity["margin_fraction_per_asset"] == 0.12
    assert capacity["maximum_margin_fraction"] == 0.60
    assert capacity["p99_stop_wave_loss_usd"] == 286.9383434980635
    assert len(routes) == 6
    assert {row["strategy_id"] for row in routes} == {
        "hulk_expansion_short_robust_v3",
        "liquidity_sweep_long_1h_stop60_target60_v2",
        "range_onset_bidirectional_v1",
        "hype_breakout_compression_pullback_bidirectional_v1",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2",
    }
    assert artifact["snapshot"]["status"] == "ready"
    assert "execution_authority" not in json.dumps(artifact).lower()


def test_report_reconciles_live_checkpoint_and_uses_portable_sources() -> None:
    """Live totals and local evidence paths must remain source-reconciled."""
    module = _load_module()
    paths = module.default_report_paths(ROOT)
    artifact = module.build_report_artifact(paths)
    datasets = artifact["snapshot"]["datasets"]
    checkpoint = json.loads(paths.checkpoint.read_text(encoding="utf-8"))
    expected = checkpoint["audit"]["trade_reflections"]["performance"]

    assert (
        datasets["all_time"][0]["closed_trades"]
        == expected["all_time_live"]["total"]["closed_trades"]
    )
    assert (
        datasets["current_run"][0]["closed_trades"]
        == expected["current_run"]["total"]["closed_trades"]
    )
    assert (
        sum(row["closed_trades"] for row in datasets["all_time_routes"])
        == expected["all_time_live"]["total"]["closed_trades"]
    )
    assert all(not Path(source["path"]).is_absolute() for source in artifact["sources"])
    assert len(artifact["manifest"]["charts"]) >= 3
    regime_rows = datasets["regime_accuracy"]
    down_clusters = next(
        row
        for row in regime_rows
        if row["horizon"] == "60m" and row["series"] == "down clusters"
    )
    assert down_clusters["observations"] == 12
    assert down_clusters["accuracy_pct"] == 83.33333333333333
    regime_chart = next(
        chart
        for chart in artifact["manifest"]["charts"]
        if chart["dataset"] == "regime_accuracy"
    )
    assert regime_chart["title"] == (
        "Regime accuracy: pooled, onset, and clustered observations"
    )
