"""Project SP500 recovery evidence into the V58 hypothesis ledger."""

from __future__ import annotations

from collections.abc import Mapping


def attach_sp500_recovery_to_ledger(
    report: dict[str, object], recovery: Mapping[str, object]
) -> None:
    """Attach one source-bound SP500 recovery result without inviting replay."""
    ledger = report.get("hypothesis_ledger")
    if not isinstance(ledger, list):
        raise ValueError("V58 hypothesis ledger is invalid")
    matches = [
        row
        for row in ledger
        if isinstance(row, dict) and row.get("symbol") == "xyz:SP500"
    ]
    if len(matches) != 1:
        raise ValueError("V58 SP500 hypothesis ledger identity is invalid")
    row = matches[0]
    row["recovery_disposition"] = recovery["disposition"]
    row["mark_risk_path_resolved"] = recovery["mark_risk_path_resolved"]
    row["prospective_decision_path_resolved"] = recovery[
        "prospective_decision_path_resolved"
    ]
    row["full_lifecycle_path_resolved"] = recovery["full_lifecycle_path_resolved"]
    row["watch_state"] = "CENSORED_AWAIT_NEW_EVIDENCE_OR_LIFECYCLE"
    row["next_action"] = "do_not_replay_unchanged_inputs"
    row["missing_prospective_decision_boundaries_ms"] = recovery[
        "missing_prospective_decision_boundaries_ms"
    ]
    row["minimum_additional_evidence"] = recovery["minimum_additional_evidence"]
    history_key = "mechanism_compatible_lifecycle_summary"
    row[history_key] = recovery[history_key]
