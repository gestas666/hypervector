"""Report-only v52 HYPE maximum-hold remediation proposal contract."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.cohort_change_proposals import normalize_change_proposals


ROOT = Path(__file__).parents[1]
OVERRIDES = ROOT / "configs/research/cohort_improvement_decision_overrides_v52.json"
PROPOSAL = (
    ROOT / "docs/research-journal/v52-hype-maximum-hold-evidence-freshness-v1.json"
)
PROPOSAL_ID = "v52-hype-maximum-hold-evidence-freshness-v1"


def test_v52_monitor_surfaces_approved_hype_maximum_hold_repair() -> None:
    """The monitor must expose the validated repair under standing approval."""
    payload = json.loads(OVERRIDES.read_text())
    proposals = normalize_change_proposals(payload["change_proposals"])
    proposal = next(row for row in proposals if row["proposal_id"] == PROPOSAL_ID)

    assert proposal["approval_status"] == "approved_waiting_flat_boundary"
    assert proposal["execution_effect"] == "approved_not_deployed"
    assert proposal["explicit_approval_requested"] is False
    assert proposal["automatic_live_change"] is False
    assert proposal["approval_evidence"].endswith(
        "v51-standing-required-change-preapproval-v1.json"
    )
    assert proposal["proposed_live_change"].startswith(
        "Implement and test a versioned HYPE maximum-hold evidence freshness"
    )


def test_v52_monitor_binds_the_proposal_source_identity() -> None:
    """The proposal file must be immutable evidence in the override manifest."""
    payload = json.loads(OVERRIDES.read_text())
    relative = PROPOSAL.relative_to(OVERRIDES.parent.parent.parent)
    matches = [row for row in payload["evidence"] if row["path"] == f"../../{relative}"]

    assert len(matches) == 1
    evidence = matches[0]
    assert evidence["bytes"] == PROPOSAL.stat().st_size
    assert len(evidence["sha256"]) == 64
