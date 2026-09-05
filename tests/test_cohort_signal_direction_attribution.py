"""Configured-direction provenance in causal signal diagnostics."""

from __future__ import annotations

from cohort_signal_outcomes_fixtures import (
    RUN_ID,
    STRATEGY,
    asset_rows,
    cohort_rows,
    first_object,
    payload,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run


def test_single_configured_side_is_labeled_as_counterfactual_attribution() -> None:
    """A one-sided hold is measurable without claiming provider-native direction."""
    rows = cohort_rows()
    identity_provider = first_object(payload(rows[0]), "providers")
    identity_provider.update({"sides": ["long"], "execution_side_overrides": {}})
    evaluation = first_object(payload(rows[1]), "evaluations")
    evaluation.update({"eligible": False, "side": None, "reason": "no_trigger"})
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness.update({"side": None, "blockers": ["sweep_absent"]})

    report = audit_multi_asset_live_run(rows, {"BTC": asset_rows()}, run_id=RUN_ID)

    outcomes = report["signal_outcomes"]
    bucket = outcomes["by_provider_symbol"][f"{STRATEGY}|BTC"]
    assert bucket["readiness_annotations"] == 1
    assert bucket["configured_direction_annotations"] == 1
    assert bucket["no_direction"] == 0
    assert bucket["by_side"]["long"]["evaluations"] == 1
    assert outcomes["contract"]["configured_direction_attribution"] == (
        "counterfactual_only"
    )
