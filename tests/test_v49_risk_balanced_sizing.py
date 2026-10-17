"""Tests for the report-only v49 risk-balanced sizing comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.v49_risk_balanced_sizing import (
    build_v49_risk_balanced_sizing,
)

_SOURCE = Path(
    "data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json"
)


def _source() -> dict[str, object]:
    return {
        "schema_version": "v49_portfolio_friction_stress_v1",
        "profile_id": "multi_asset_growth_first_5000_repaired_candidate_v49",
        "profile_fingerprint": "fingerprint",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_sizing_change": False,
            "runtime_strategy_changed": False,
        },
        "sizing_policy": {"configured_leverage": 10.0},
        "scenarios": [
            {
                "account_value_usd": 5000.0,
                "route_aware_maximum_margin_fraction": 0.3,
                "stacked_p99_stop_wave_loss_usd": 225.0,
                "stacked_p99_stop_wave_loss_pct_equity": 4.5,
                "asset_slots": {
                    "BTC": {
                        "maximum_margin_fraction": 0.15,
                        "stacked_p99_slot_loss_usd": 75.0,
                        "routes": [{"planned_notional_usd": 7500.0}],
                    },
                    "ETH": {
                        "maximum_margin_fraction": 0.15,
                        "stacked_p99_slot_loss_usd": 150.0,
                        "routes": [{"planned_notional_usd": 7500.0}],
                    },
                },
            }
        ],
    }


def test_inverse_p99_sizing_preserves_exposure_and_equalizes_loss() -> None:
    """Inverse intensity keeps total exposure while equalizing p99 dollars."""
    report = build_v49_risk_balanced_sizing(_source())

    assert report["contract"]["execution_authority"] == "none"
    assert report["comparison"]["total_margin_fraction"] == pytest.approx(0.3)
    assert report["comparison"]["total_notional_usd"] == pytest.approx(15000.0)
    assert report["comparison"]["baseline_p99_loss_usd"] == pytest.approx(225.0)
    assert report["comparison"]["candidate_p99_loss_usd"] == pytest.approx(200.0)
    assert report["comparison"]["baseline_p99_max_min_ratio"] == pytest.approx(2.0)
    assert report["comparison"]["candidate_p99_max_min_ratio"] == pytest.approx(1.0)
    rows = report["by_asset"]
    assert rows["BTC"]["candidate_margin_fraction"] == pytest.approx(0.2)
    assert rows["ETH"]["candidate_margin_fraction"] == pytest.approx(0.1)
    assert rows["BTC"]["candidate_p99_loss_usd"] == pytest.approx(100.0)
    assert rows["ETH"]["candidate_p99_loss_usd"] == pytest.approx(100.0)


@pytest.mark.evidence
def test_real_v49_comparison_remains_report_only_and_capital_neutral() -> None:
    """The frozen v49 evidence produces a bounded four-asset comparison."""
    report = build_v49_risk_balanced_sizing(json.loads(_SOURCE.read_text()))

    assert report["profile_id"] == (
        "multi_asset_growth_first_5000_repaired_candidate_v49"
    )
    assert set(report["by_asset"]) == {"BTC", "ETH", "SOL", "HYPE"}
    assert report["comparison"]["total_margin_fraction"] == pytest.approx(0.6)
    assert report["comparison"]["total_notional_usd"] == pytest.approx(30000.0)
    losses = [row["candidate_p99_loss_usd"] for row in report["by_asset"].values()]
    assert max(losses) == pytest.approx(min(losses))
    assert report["contract"]["automatic_sizing_change"] is False


def test_malformed_source_is_rejected() -> None:
    """Sizing evidence cannot acquire authority or accept inconsistent totals."""
    source = _source()
    source["contract"]["execution_authority"] = "live"
    with pytest.raises(ValueError, match="report-only"):
        build_v49_risk_balanced_sizing(source)
