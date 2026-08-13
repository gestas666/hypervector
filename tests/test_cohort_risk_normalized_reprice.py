"""Exact-notional repricing audit for the frozen risk-normalized allocation."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_risk_normalized_allocation import (
    build_risk_normalized_allocation,
)
from hypervector.research.cohort_risk_normalized_reprice import (
    ExactVisibleCost,
    build_exact_reprice_audit,
)


def test_reprices_frozen_allocation_without_silently_reoptimizing_it() -> None:
    """Exact liquidity changes losses while keeping candidate notionals fixed."""
    source = _source()
    allocation = build_risk_normalized_allocation(source)
    exact = {
        symbol: ExactVisibleCost(
            notional_usd=row["candidate_notional_usd"],
            sample_count=240,
            complete_rate=1.0,
            p50=4.0,
            p90=7.0,
            p99=10.0,
            evidence_source=f"exact-{symbol}",
        )
        for symbol, row in allocation["by_asset"].items()
    }

    audit = build_exact_reprice_audit(source, allocation, exact)

    assert audit["mode"] == "cohort_p99_risk_normalized_exact_reprice_v1"
    assert audit["status"] == "exact_notional_repriced"
    assert audit["contract"]["execution_authority"] == "none"
    assert audit["allocation_reoptimized_after_reprice"] is False
    assert audit["by_asset"]["A"]["candidate_notional_usd"] == pytest.approx(
        allocation["by_asset"]["A"]["candidate_notional_usd"]
    )
    assert audit["by_asset"]["A"]["repriced_p99_total_loss_bps"] == pytest.approx(105.0)
    assert (
        audit["portfolio_comparison"]["repriced_candidate"]["p99_stop_wave_loss_usd"]
        > 0.0
    )
    assert audit["exact_notional_repricing_complete"] is True


def test_rejects_visible_evidence_for_a_different_notional() -> None:
    """A nearby liquidity profile cannot masquerade as exact repricing."""
    source = _source()
    allocation = build_risk_normalized_allocation(source)
    exact = {
        symbol: ExactVisibleCost(
            notional_usd=row["candidate_notional_usd"],
            sample_count=240,
            complete_rate=1.0,
            p50=4.0,
            p90=7.0,
            p99=10.0,
            evidence_source=f"exact-{symbol}",
        )
        for symbol, row in allocation["by_asset"].items()
    }
    exact["A"] = ExactVisibleCost(1.0, 240, 1.0, 4.0, 7.0, 10.0, "wrong")

    with pytest.raises(ValueError, match="A exact notional does not match allocation"):
        build_exact_reprice_audit(source, allocation, exact)


def _source() -> dict[str, object]:
    by_asset = {
        "A": _asset(90.0, 95.0, 100.0),
        "B": _asset(100.0, 110.0, 120.0),
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


def _asset(p50: float, p90: float, p99: float) -> dict[str, object]:
    return {
        "visible_cost_sample_count": 240,
        "visible_depth_complete_rate": 1.0,
        "p50": _scenario(p50),
        "p90": _scenario(p90),
        "p99": _scenario(p99),
    }


def _scenario(total_bps: float) -> dict[str, float]:
    visible = 5.0
    return {
        "adverse_exit_visible_cost_bps": visible,
        "total_loss_bps": total_bps,
        "total_loss_usd": 750.0 * total_bps / 10_000.0,
    }
