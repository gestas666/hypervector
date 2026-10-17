"""Acceptance tests for the source-backed v48 readiness report."""

from __future__ import annotations

import pytest

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "v48_portfolio_readiness_report.py"


@pytest.mark.evidence
def test_report_is_answer_first_and_exact_v48_bound() -> None:
    """The report must lead with the decision and exact successor identity."""
    module = _module()
    artifact = module.build_report_artifact(module.default_report_paths(ROOT))
    blocks = artifact["manifest"]["blocks"]
    datasets = artifact["snapshot"]["datasets"]
    capacity = datasets["candidate_capacity"][0]

    assert artifact["manifest"]["title"] == "Hypervector $5K Growth Readiness"
    assert blocks[0]["body"] == "# Hypervector $5K Growth Readiness"
    assert blocks[1]["body"].startswith("## Executive Summary")
    assert capacity["profile_id"].endswith("v48")
    assert capacity["usable_asset_slots"] == 4
    assert capacity["maximum_margin_fraction"] == 0.6
    assert capacity["p99_stop_wave_loss_usd"] == 294.7042017546197
    assert len(datasets["candidate_routes"]) == 5
    assert {row["asset"] for row in datasets["candidate_routes"]} == {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
    }
    assert datasets["defect_summary"] == [
        {
            "affected_closed_trades": 5,
            "affected_net_pnl_usd": -2.713721,
            "affected_loss_fraction": 0.6373019675257272,
        }
    ]


@pytest.mark.evidence
def test_report_reconciles_checkpoint_sources_and_visual_context() -> None:
    """Every visual and exact metric must remain source-auditable."""
    module = _module()
    paths = module.default_report_paths(ROOT)
    artifact = module.build_report_artifact(paths)
    datasets = artifact["snapshot"]["datasets"]
    checkpoint = json.loads(paths.checkpoint.read_text())
    expected = checkpoint["audit"]["trade_reflections"]["performance"]
    sources = artifact["manifest"]["sources"]
    source_ids = {source["id"] for source in sources}

    assert (
        datasets["all_time"][0]["closed_trades"]
        == (expected["all_time_live"]["total"]["closed_trades"])
    )
    assert "v48-config" in source_ids and "v48-stress" in source_ids
    parity = next(source for source in sources if source["id"] == "hip3-parity")
    assert parity["path"].endswith("hip3-live-pressure-freshness-parity-v3.json")
    assert all(source["id"] not in {"v47-config", "v47-stress"} for source in sources)
    assert all(not Path(source["path"]).is_absolute() for source in sources)
    regime_chart = next(
        chart
        for chart in artifact["manifest"]["charts"]
        if chart["id"] == "regime-accuracy"
    )
    assert regime_chart["dataset"] == "regime_cluster_accuracy"
    assert {row["series"] for row in datasets["regime_cluster_accuracy"]} == {
        "up clusters",
        "down clusters",
    }
    _assert_visual_context(artifact["manifest"])


def _assert_visual_context(manifest: dict[str, object]) -> None:
    blocks = manifest["blocks"]
    for index, block in enumerate(blocks):
        if block["type"] != "chart":
            continue
        neighbors = blocks[max(0, index - 1) : index] + blocks[index + 1 : index + 2]
        assert any(neighbor["type"] == "markdown" for neighbor in neighbors)
    for table in manifest["tables"]:
        fields = {column["field"] for column in table["columns"]}
        assert table["defaultSort"]["field"] in fields


def _module() -> ModuleType:
    spec = spec_from_file_location("v48_portfolio_readiness_report", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v48 readiness report")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
