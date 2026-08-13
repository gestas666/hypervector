"""Tests for report-only provider-family concentration evidence."""

from __future__ import annotations

from importlib import import_module

import pytest


def test_overlapping_provider_scopes_form_connected_risk_clusters() -> None:
    """Shared provider symbols must aggregate into one joint-loss cluster."""
    module = import_module("hypervector.research.cohort_family_concentration")
    report = module.build_family_concentration_report(
        _allocation(),
        {
            "provider_ab": ("A", "B"),
            "provider_b": ("B",),
            "provider_c": ("C",),
        },
        target_equity_usd=1_000.0,
    )

    assert report["mode"] == "cohort_provider_family_concentration_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["portfolio"]["p99_stop_wave_loss_usd"] == pytest.approx(20.0)
    assert report["portfolio"]["largest_cluster_share_pct"] == pytest.approx(60.0)
    assert report["by_provider"]["provider_ab"]["p99_loss_usd"] == pytest.approx(12.0)
    assert report["clusters"] == [
        {
            "cluster_id": "cluster_1",
            "symbols": ["A", "B"],
            "providers": ["provider_ab", "provider_b"],
            "p99_loss_usd": pytest.approx(12.0),
            "p99_loss_pct_equity": pytest.approx(1.2),
            "share_of_portfolio_stop_wave_pct": pytest.approx(60.0),
        },
        {
            "cluster_id": "cluster_2",
            "symbols": ["C"],
            "providers": ["provider_c"],
            "p99_loss_usd": pytest.approx(8.0),
            "p99_loss_pct_equity": pytest.approx(0.8),
            "share_of_portfolio_stop_wave_pct": pytest.approx(40.0),
        },
    ]


def test_missing_execution_scope_asset_fails_closed() -> None:
    """Every risk-sized asset must be bound to an executable provider scope."""
    module = import_module("hypervector.research.cohort_family_concentration")

    with pytest.raises(ValueError, match="provider scopes omit allocation assets: C"):
        module.build_family_concentration_report(
            _allocation(),
            {"provider_ab": ("A", "B")},
            target_equity_usd=1_000.0,
        )


def _allocation() -> dict[str, object]:
    return {
        "mode": "cohort_p99_risk_normalized_exact_reprice_v1",
        "status": "report_only_candidate",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_sizing_change": False,
            "automatic_promotion": False,
            "performance_gate": False,
            "balance_gate": False,
        },
        "source_identity": {
            "profile_id": "candidate",
            "profile_fingerprint": "f" * 64,
        },
        "by_asset": {
            "A": {"repriced_p99_loss_usd": 5.0},
            "B": {"repriced_p99_loss_usd": 7.0},
            "C": {"repriced_p99_loss_usd": 8.0},
        },
    }
