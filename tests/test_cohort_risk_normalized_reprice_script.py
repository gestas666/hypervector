"""Command wiring for exact-notional risk-normalized repricing."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_risk_normalized_allocation import (
    build_risk_normalized_allocation,
)
from hypervector.research.cohort_risk_normalized_reprice import ExactVisibleCost

SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_risk_normalized_reprice.py"
SPEC = spec_from_file_location("cohort_risk_normalized_reprice_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_run_report_binds_inputs_and_exact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command joins exact evidence without granting execution authority."""
    source_value = _source()
    allocation_value = build_risk_normalized_allocation(source_value)
    source = tmp_path / "source.json"
    allocation = tmp_path / "allocation.json"
    active_config = tmp_path / "active.toml"
    source.write_text(json.dumps(source_value), encoding="utf-8")
    allocation.write_text(json.dumps(allocation_value), encoding="utf-8")
    active_config.write_text("profile_id = 'fixture'\n", encoding="utf-8")
    exact = {
        symbol: ExactVisibleCost(
            notional_usd=row["candidate_notional_usd"],
            sample_count=240,
            complete_rate=1.0,
            p50=1.0,
            p90=2.0,
            p99=3.0,
            evidence_source=f"exact-{symbol}",
        )
        for symbol, row in allocation_value["by_asset"].items()
    }
    monkeypatch.setattr(
        MODULE,
        "_collect_exact_evidence",
        lambda *_args: (exact, {"status": "fixture"}),
    )
    args = argparse.Namespace(
        source=source,
        allocation=allocation,
        active_config=active_config,
        hip3_profile=(),
        out=tmp_path / "report.json",
    )

    report = MODULE.run_report(args)

    assert report["mode"] == "cohort_p99_risk_normalized_exact_reprice_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["exact_evidence"] == {"status": "fixture"}
    assert report["source_evidence"]["growth_stress"]["sha256"]
    assert report["source_evidence"]["allocation"]["sha256"]


def test_parses_worst_side_from_exact_core_and_hip3_profiles() -> None:
    """Long and short liquidity remain symmetric inputs to the audit."""
    core = MODULE._core_exact_cost(
        {
            "notional_usd": 800.0,
            "snapshot_count": 240,
            "buy_complete_rate": 1.0,
            "sell_complete_rate": 0.9,
            "buy_visible_cost_bps": {"p50": 1.0, "p90": 2.0, "p99": 3.0},
            "sell_visible_cost_bps": {"p50": 1.5, "p90": 1.8, "p99": 4.0},
        },
        "core-ledger",
    )
    hip3 = MODULE._hip3_exact_cost(
        {
            "notionals": [
                {
                    "notional_usd": 600.0,
                    "samples": 100,
                    "buy_complete_rate": 0.95,
                    "sell_complete_rate": 1.0,
                    "buy_visible_cost_bps": {"p50": 2.0, "p90": 3.0, "p99": 5.0},
                    "sell_visible_cost_bps": {"p50": 1.0, "p90": 4.0, "p99": 4.5},
                }
            ]
        },
        "hip3-db",
    )

    assert core == ExactVisibleCost(800.0, 240, 0.9, 1.5, 2.0, 4.0, "core-ledger")
    assert hip3 == ExactVisibleCost(600.0, 100, 0.95, 2.0, 4.0, 5.0, "hip3-db")


def _source() -> dict[str, object]:
    by_asset = {"A": _asset(90.0), "B": _asset(110.0)}
    return {
        "schema_version": 3,
        "mode": "cohort_growth_sizing_stress_v3",
        "profile_id": "growth-v40",
        "profile_fingerprint": "f" * 64,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_sizing_change": False,
            "performance_gate": False,
            "balance_gate": False,
            "profit_forecast": False,
        },
        "sizing_plan": {
            "target_equity_usd": 5_000.0,
            "margin_fraction_per_slot": 0.03,
            "leverage": 5.0,
            "planned_notional_usd_per_slot": 750.0,
            "configured_assets": 2,
            "maximum_positions": 10,
            "actual_roster_maximum_margin_fraction": 0.06,
        },
        "by_asset": by_asset,
        "portfolio_stress": {
            "configured_asset_roster": {
                f"{quantile}_stop_wave_loss_usd": sum(
                    row[quantile]["total_loss_usd"] for row in by_asset.values()
                )
                for quantile in ("p50", "p90", "p99")
            }
        },
    }


def _asset(p99: float) -> dict[str, object]:
    return {
        "visible_cost_sample_count": 240,
        "visible_depth_complete_rate": 1.0,
        "p50": _scenario(p99 - 10.0),
        "p90": _scenario(p99 - 5.0),
        "p99": _scenario(p99),
    }


def _scenario(total: float) -> dict[str, float]:
    return {
        "adverse_exit_visible_cost_bps": 2.0,
        "total_loss_bps": total,
        "total_loss_usd": 750.0 * total / 10_000.0,
    }
