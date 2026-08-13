"""Acceptance tests for the v39-to-v45 growth-readiness report."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from v39_v45_growth_report_fixtures import fixture_paths, report_inputs


SCRIPT = Path(__file__).parents[1] / "scripts" / "v39_v45_growth_report.py"
ROOT = Path(__file__).parents[1]


def _load_module() -> ModuleType:
    spec = spec_from_file_location("v39_v45_growth_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_report(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], object]:
    """Build a report from immutable in-memory evidence."""
    inputs = report_inputs()
    paths = fixture_paths(ROOT, module.ReportPaths)
    monkeypatch.setattr(module, "_load", lambda path: inputs[path.name])
    return module.build_report_artifact(paths), paths


def test_growth_report_reconciles_frozen_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The report must preserve exact frozen totals and candidate identity."""
    module = _load_module()
    artifact, paths = _fixture_report(module, monkeypatch)
    datasets = artifact["snapshot"]["datasets"]
    checkpoint = report_inputs()[paths.checkpoint.name]
    performance = checkpoint["audit"]["trade_reflections"]["performance"]

    assert artifact["surface"] == "report"
    assert (
        datasets["current_run"][0]["closed_trades"]
        == performance["current_run"]["total"]["closed_trades"]
    )
    assert (
        datasets["all_time"][0]["closed_trades"]
        == performance["all_time_live"]["total"]["closed_trades"]
    )
    assert sum(row["closed_trades"] for row in datasets["all_time_routes"]) == 2
    assert datasets["v45_policy"][0]["leverage_policy"] == "fixed_5x"
    assert datasets["v45_policy"][0]["sizing_policy"] == "adaptive_notional_only"
    assert datasets["v45_capacity"][0]["actual_asset_slots"] == 3
    assert all(not Path(source["path"]).is_absolute() for source in artifact["sources"])
    assert "v44" not in json.dumps(artifact).lower()


def test_variable_notional_tiers_have_no_execution_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No report revision may turn sizing hypotheses into live authority."""
    module = _load_module()
    artifact, _ = _fixture_report(module, monkeypatch)
    sizing = artifact["snapshot"]["datasets"]["variable_sizing_status"][0]

    assert sizing["execution_authority"] == "none"
    assert sizing["tier_authority"] == "counterfactual_only"
    assert sizing["eligible_candidates"] == 0
    assert sizing["selected_tier_policy"] == "withheld_pending_forward_outcomes"
