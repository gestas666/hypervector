"""Approval-bound transition-drain proposal contract for v51."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.cohort_change_proposals import normalize_change_proposals

_OVERRIDES = Path("configs/research/cohort_improvement_decision_overrides_v51.json")


def test_v51_transition_drain_records_approved_active_containment() -> None:
    """Keep the activated containment visible without deployment authority."""
    payload = json.loads(_OVERRIDES.read_text(encoding="utf-8"))

    proposals = normalize_change_proposals(payload["change_proposals"])

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["proposal_id"] == "v51-transition-drain-containment-v1"
    assert proposal["approval_status"] == ("approved_activated_waiting_flat_boundary")
    assert proposal["execution_effect"] == "approved_active_transition_drain"
    assert proposal["automatic_live_change"] is False
    assert proposal["explicit_approval_requested"] is False
    assert proposal["approval_evidence"].endswith(
        "v51-transition-drain-approval-activation-v1.json"
    )
    assert "transition drain" in str(proposal["proposed_live_change"]).lower()


def test_activated_transition_drain_preserves_approval_evidence() -> None:
    """An activated drain needs an honest non-deployment authority state."""
    payload = json.loads(_OVERRIDES.read_text(encoding="utf-8"))
    proposal = dict(payload["change_proposals"][0])
    proposal.update(
        {
            "approval_status": "approved_activated_waiting_flat_boundary",
            "approval_evidence": "activation-evidence.json",
            "execution_effect": "approved_active_transition_drain",
            "explicit_approval_requested": False,
        }
    )

    actual = normalize_change_proposals([proposal])[0]

    assert actual["approval_status"] == ("approved_activated_waiting_flat_boundary")
    assert actual["approval_evidence"] == "activation-evidence.json"
