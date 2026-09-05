"""Cross-layer contract for the route-native one-blocker shadow experiment."""

from __future__ import annotations

import pytest

import hypervector.research.cohort_continuous_improvement as continuous
import hypervector.research.cohort_improvement_digest as digest
from hypervector.research.cohort_opportunity_ranking import (
    rank_research_opportunities,
)
from test_cohort_improvement_digest import _audit, _sides, _triage

_EXPERIMENT = "collect_route_native_one_blocker_shadow"


def test_route_native_one_blocker_shadow_is_supported_across_research_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source-bound override must survive digest, normalization, and ranking."""
    monkeypatch.setattr(digest, "build_successor_triage", lambda audit: _triage())
    monkeypatch.setattr(digest, "build_side_composition", lambda audit: _sides())
    report = digest.build_cohort_improvement_digest(
        _audit(), experiment_overrides=_overrides()
    )
    row = next(
        item for item in report["experiment_queue"] if item["route"] == "range|SOL"
    )
    assert row["next_experiment"] == _EXPERIMENT
    normalized = continuous._normalize_row(
        row,
        {"range|SOL": ["long", "short"]},
        {"range|SOL": {"research_state": "forward_unresolved"}},
    )
    ranked = rank_research_opportunities(
        [normalized], {"range|SOL": {"confidence": "low"}}
    )
    assert ranked[0]["experiment"] == _EXPERIMENT
    assert ranked[0]["expected_information_value"] == "high"
    assert ranked[0]["execution_effect"] == "report_only"
    assert ranked[0]["automatic_live_change"] is False


def _overrides() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {
            "range|SOL": {
                "triage": "REVISE",
                "next_experiment": _EXPERIMENT,
                "historical_assessment": "one_blocker_forward_lead",
                "decision_source": "sol-one-blocker-v3.json",
            }
        },
    }
