"""Regression coverage for the V58 SP500 recovery-ledger projection."""

from __future__ import annotations

from hypervector.research.v58_sp500_recovery_ledger import (
    attach_sp500_recovery_to_ledger,
)


def test_recovered_decision_censor_waits_for_new_evidence_not_same_replay() -> None:
    """A completed failed recovery must not remain labeled replay-due."""
    report = {
        "hypothesis_ledger": [
            {
                "symbol": "xyz:SP500",
                "watch_state": "LIFECYCLE_REPLAY_CANDIDATE_DUE",
                "pending_lifecycles": 1,
                "technical_complete": False,
            }
        ]
    }
    recovery = {
        "disposition": "OPEN_LIFECYCLE_CENSORED_DECISION_GAP",
        "mark_risk_path_resolved": True,
        "prospective_decision_path_resolved": False,
        "full_lifecycle_path_resolved": False,
        "missing_prospective_decision_boundaries_ms": [1787125500000],
        "minimum_additional_evidence": "new boundary evidence or a new lifecycle",
        "mechanism_compatible_lifecycle_summary": {},
    }

    attach_sp500_recovery_to_ledger(report, recovery)

    row = report["hypothesis_ledger"][0]
    assert row["watch_state"] == "CENSORED_AWAIT_NEW_EVIDENCE_OR_LIFECYCLE"
    assert row["next_action"] == "do_not_replay_unchanged_inputs"
    assert row["missing_prospective_decision_boundaries_ms"] == [1787125500000]
    assert row["minimum_additional_evidence"] == recovery["minimum_additional_evidence"]
    assert row["pending_lifecycles"] == 1
