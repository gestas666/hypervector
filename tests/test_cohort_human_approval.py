"""Standing human-approval contracts for the continuous-improvement loop."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_human_approval import (
    build_human_approval_boundary,
    normalize_standing_live_change_approval,
)


def test_missing_standing_approval_preserves_explicit_approval_gate() -> None:
    """An absent operator decision must retain the fail-closed boundary."""
    boundary = build_human_approval_boundary(None)

    assert boundary["required_before_live_change"] is True
    assert boundary["agent_may_apply_after_validation"] is False
    assert boundary["current_authority"] == "research_and_diagnostics_only"
    assert boundary["execution_authority"] == "none"


def test_standing_approval_removes_duplicate_prompt_inside_exact_scope() -> None:
    """Validated remediation may proceed without asking for the same approval."""
    approval = normalize_standing_live_change_approval(_approval())
    boundary = build_human_approval_boundary(approval)

    assert boundary["required_before_live_change"] is False
    assert boundary["required_outside_approved_scope"] is True
    assert boundary["agent_may_apply_after_validation"] is True
    assert boundary["agent_reapproval_required"] is False
    assert boundary["automatic_live_change"] is False
    assert boundary["live_arming_flags_required"] is True
    assert boundary["approval_evidence"] == "operator-approval.json"
    assert boundary["approved_scope"] == _approval()["approved_scope"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automatic_live_change", True),
        ("live_arming_flags_required", False),
        ("validation_required", False),
        ("rollback_required", False),
        ("agent_may_apply_after_validation", False),
        ("agent_reapproval_required", True),
    ],
)
def test_standing_approval_rejects_weakened_safety_contract(
    field: str, value: bool
) -> None:
    """Standing authority cannot weaken validation or live arming controls."""
    approval = _approval()
    approval[field] = value

    with pytest.raises(ValueError, match="standing approval contract is invalid"):
        normalize_standing_live_change_approval(approval)


def _approval() -> dict[str, object]:
    return {
        "approval_status": "standing_preapproved_for_validated_required_changes",
        "approval_evidence": "operator-approval.json",
        "approved_scope": [
            "verified technical defects",
            "verified broken strategy logic",
            "evidence-supported capital-loss containment",
        ],
        "excluded_scope": ["speculative unvalidated exposure increases"],
        "agent_may_apply_after_validation": True,
        "agent_reapproval_required": False,
        "automatic_live_change": False,
        "live_arming_flags_required": True,
        "validation_required": True,
        "rollback_required": True,
    }
