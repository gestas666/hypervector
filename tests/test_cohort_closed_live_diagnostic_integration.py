"""Integration contract for closed one-blocker research dispositions."""

from __future__ import annotations

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from test_cohort_continuous_improvement import (
    _attach_live_diagnostics,
    _checkpoint,
    _digest,
)
from test_cohort_live_opportunity_diagnostics import _audit as _diagnostic_audit


def test_continuous_report_does_not_reopen_closed_one_blocker_path() -> None:
    """The merged hypothesis ledger must disposition matching live diagnostics."""
    checkpoint = _checkpoint()
    _attach_live_diagnostics(checkpoint)
    source = _diagnostic_audit()
    audit = checkpoint["audit"]
    audit["readiness"]["by_provider_symbol"]["range|SOL"] = source["readiness"][
        "by_provider_symbol"
    ]["strategy|SOL"]
    audit["signal_outcomes"]["by_provider_symbol"]["range|SOL"] = source[
        "signal_outcomes"
    ]["by_provider_symbol"]["strategy|SOL"]
    digest = _digest()
    digest["research_decision_overrides"] = {
        "active_hypotheses": [],
        "hypothesis_decisions": [_closed_decision()],
        "change_proposals": [],
        "standing_live_change_approval": None,
    }

    report = build_continuous_improvement_report(checkpoint, digest)

    diagnostics = report["live_opportunity_diagnostics"]
    route = next(row for row in diagnostics["routes"] if row["route"] == "range|SOL")
    assert route["one_blocker_paths"][0]["assessment"] == (
        "closed_by_hypothesis_decision"
    )
    assert diagnostics["robust_report_only_leads"] == []


def _closed_decision() -> dict[str, object]:
    return {
        "hypothesis_id": "closed-range-gate",
        "route": "range|SOL",
        "experiment": "remove_gate",
        "status": "rejected",
        "decision_reason": "the preregistered replay lost after costs",
        "decision_source": "closed-range-gate.json",
        "reopen_condition": "a distinct preregistered causal window",
        "closed_live_diagnostic_blockers": ["gate_absent"],
    }
