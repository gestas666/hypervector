"""Immutable command coverage for the risk-normalized growth challenger."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_growth_sizing_stress import (
    AssetGrowthStressInput,
    VisibleCostQuantiles,
    build_growth_sizing_stress,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_risk_normalized_allocation.py"
SPEC = spec_from_file_location("cohort_risk_normalized_allocation_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_builds_source_bound_report_and_refuses_replacement(tmp_path: Path) -> None:
    """Published evidence binds the exact source and cannot replace itself."""
    source = tmp_path / "growth.json"
    output = tmp_path / "allocation.json"
    source.write_text(json.dumps(_source()), encoding="utf-8")
    args = argparse.Namespace(source=source, out=output)

    report = MODULE.run_report(args)

    assert report["mode"] == "cohort_p99_risk_normalized_allocation_v1"
    assert report["source_evidence"]["path"] == str(source)
    assert report["source_evidence"]["sha256"]
    assert report["generator_identity"]["tree_sha256"]
    MODULE.write_immutable_report(output, report)
    assert (
        json.loads(output.read_text(encoding="utf-8"))["contract"][
            "execution_authority"
        ]
        == "none"
    )
    with pytest.raises(FileExistsError, match="allocation output already exists"):
        MODULE.write_immutable_report(output, report)


def _source() -> dict[str, object]:
    report = build_growth_sizing_stress(
        equity_usd=5_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        maximum_positions=10,
        assets=tuple(_asset(symbol, index) for index, symbol in enumerate("ABCD")),
    )
    report["profile_id"] = "growth-v40"
    report["profile_fingerprint"] = "f" * 64
    return report


def _asset(symbol: str, index: int) -> AssetGrowthStressInput:
    visible = 1.0 + index
    return AssetGrowthStressInput(
        symbol=symbol,
        stop_bps=80.0 + index * 5.0,
        one_way_taker_fee_bps=4.5,
        visible_cost=VisibleCostQuantiles(240, 1.0, visible, visible, visible),
        latest_hourly_funding_rate=0.00001,
        current_profile_cap_usd=750.0,
    )
