"""Minimum evidence contract for the V58 ETH risk-lock hypothesis."""

from __future__ import annotations

from collections.abc import Mapping

_ROUTE = "eth_breakout_precompression_pullback_bidirectional_v1|ETH"


def minimum_evidence(lifecycle_state: object) -> dict[str, object]:
    """Return diagnostic and live-change evidence requirements for ETH."""
    if lifecycle_state not in {"open", "closed", "not_observed_current_run"}:
        raise ValueError("V58 ETH lifecycle state is invalid")
    return {
        "current_lifecycle_resolved": lifecycle_state == "closed",
        "new_resolved_lifecycles_per_side": 1,
        "required_sides": ["long", "short"],
        "exact_reconciliation_required": [
            "fills",
            "fees",
            "funding",
            "slippage",
            "exit_reason",
            "flat_order_free",
        ],
        "change_reconsideration_requirements": [
            "preregistered_same_mechanism",
            "exact_cost_and_gap_sensitivity",
            "positive_after_largest_winner_removal",
            "independent_resolved_long_and_short_lifecycles",
        ],
        "not_an_automatic_performance_gate": True,
        "live_change_requires_explicit_human_approval": True,
    }


def attach_eth_risk_lock_evidence_to_ledger(
    ledger: object, risk_lock_payload: Mapping[str, object]
) -> None:
    """Attach the exact ETH evidence requirement to one hypothesis row."""
    if not isinstance(ledger, list):
        raise ValueError("V58 hypothesis ledger must be an array")
    matches = [
        row for row in ledger if isinstance(row, dict) and row.get("route") == _ROUTE
    ]
    if len(matches) != 1:
        raise ValueError("V58 ETH hypothesis ledger identity is invalid")
    evidence = risk_lock_payload.get("minimum_additional_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("V58 ETH minimum evidence contract is invalid")
    matches[0]["minimum_additional_evidence"] = dict(evidence)
    _attach_review_disposition(matches[0], risk_lock_payload)


def _attach_review_disposition(
    row: dict[str, object], payload: Mapping[str, object]
) -> None:
    if payload.get("lifecycle_state") != "closed":
        return
    disposition = payload.get("historical_disposition")
    if not isinstance(disposition, Mapping):
        raise ValueError("V58 ETH historical disposition is invalid")
    if disposition.get("live_change_proposed") is not False:
        raise ValueError("V58 ETH reviewed disposition must not imply a live change")
    row["status"] = "being_tested"
    row["evidence_state"] = "reviewed_no_live_change"
    row["review_status"] = "reviewed_no_live_change"
