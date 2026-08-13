"""Risk-normalized growth allocation remains report-only and capital neutral."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_risk_normalized_allocation import (
    build_risk_normalized_allocation,
)


def test_equalizes_frozen_p99_loss_while_preserving_total_exposure() -> None:
    """Inverse-p99 sizing redistributes, rather than reducing, the risk budget."""
    report = build_risk_normalized_allocation(_growth_stress())

    assert report["mode"] == "cohort_p99_risk_normalized_allocation_v1"
    assert report["status"] == "report_only_candidate"
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "profit_forecast": False,
    }
    invariants = report["sizing_invariants"]
    assert invariants["total_margin_fraction"] == pytest.approx(0.12)
    assert invariants["total_margin_usd"] == pytest.approx(600.0)
    assert invariants["total_notional_usd"] == pytest.approx(3_000.0)

    rows = report["by_asset"]
    candidate_notionals = [row["candidate_notional_usd"] for row in rows.values()]
    candidate_losses = [row["candidate_p99_loss_usd"] for row in rows.values()]
    assert sum(candidate_notionals) == pytest.approx(3_000.0)
    assert max(candidate_losses) == pytest.approx(min(candidate_losses))
    assert rows["D"]["candidate_notional_usd"] < 750.0
    assert rows["C"]["candidate_notional_usd"] > 750.0

    portfolio = report["portfolio_comparison"]
    assert portfolio["baseline"]["p99_stop_wave_loss_usd"] == pytest.approx(34.5)
    assert portfolio["candidate"]["p99_stop_wave_loss_usd"] < 34.5
    assert portfolio["baseline"]["p99_asset_loss_max_min_ratio"] > 1.0
    assert portfolio["candidate"]["p99_asset_loss_max_min_ratio"] == pytest.approx(1.0)
    assert report["exact_notional_repricing_required"] is True


def test_rejects_inconsistent_source_loss_arithmetic() -> None:
    """Success-shaped source economics cannot enter the allocation challenger."""
    source = _growth_stress()
    source["by_asset"]["A"]["p99"]["total_loss_usd"] = 0.01

    with pytest.raises(ValueError, match="A p99 loss arithmetic is inconsistent"):
        build_risk_normalized_allocation(source)


def test_rejects_source_with_execution_or_performance_authority() -> None:
    """The candidate accepts only an ungated report-only stress artifact."""
    source = _growth_stress()
    source["contract"]["execution_authority"] = "live"

    with pytest.raises(ValueError, match="source contract is not report-only"):
        build_risk_normalized_allocation(source)


def _growth_stress() -> dict[str, object]:
    by_asset = {
        "A": _asset(90.0, 95.0, 100.0),
        "B": _asset(100.0, 110.0, 120.0),
        "C": _asset(80.0, 90.0, 90.0),
        "D": _asset(120.0, 130.0, 150.0),
    }
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
            "planned_margin_usd_per_slot": 150.0,
            "planned_notional_usd_per_slot": 750.0,
            "configured_assets": 4,
            "maximum_positions": 10,
            "actual_roster_maximum_margin_fraction": 0.12,
        },
        "by_asset": by_asset,
        "portfolio_stress": {
            "configured_asset_roster": {
                "p50_stop_wave_loss_usd": sum(
                    row["p50"]["total_loss_usd"] for row in by_asset.values()
                ),
                "p90_stop_wave_loss_usd": sum(
                    row["p90"]["total_loss_usd"] for row in by_asset.values()
                ),
                "p99_stop_wave_loss_usd": sum(
                    row["p99"]["total_loss_usd"] for row in by_asset.values()
                ),
            }
        },
    }


def _asset(p50_bps: float, p90_bps: float, p99_bps: float) -> dict[str, object]:
    return {
        "visible_cost_sample_count": 240,
        "visible_depth_complete_rate": 1.0,
        "p50": _scenario(p50_bps),
        "p90": _scenario(p90_bps),
        "p99": _scenario(p99_bps),
    }


def _scenario(total_loss_bps: float) -> dict[str, float]:
    return {
        "total_loss_bps": total_loss_bps,
        "total_loss_usd": 750.0 * total_loss_bps / 10_000.0,
    }
