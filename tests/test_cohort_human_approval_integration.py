"""Integration coverage for standing approval in the improvement digest."""

from __future__ import annotations

from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from hypervector.research.cohort_improvement_digest import (
    _apply_experiment_overrides,
)
from test_cohort_continuous_improvement import _checkpoint, _digest


def test_digest_override_summary_retains_standing_operator_approval() -> None:
    """The source-bound override must carry approval into later projections."""
    approval = _approval()
    _, summary = _apply_experiment_overrides([], _overrides(approval))

    assert summary["standing_live_change_approval"] == approval


def test_continuous_report_projects_standing_approval_without_order_authority() -> None:
    """The report must stop requesting duplicate approval yet remain report-only."""
    digest = _digest()
    digest["research_decision_overrides"] = {
        "standing_live_change_approval": _approval(),
    }

    report = build_continuous_improvement_report(_checkpoint(), digest)

    boundary = report["human_approval_boundary"]
    assert boundary["required_before_live_change"] is False
    assert boundary["agent_may_apply_after_validation"] is True
    assert boundary["execution_authority"] == "none"
    assert report["proposal_contract"]["automatic_live_change"] is False


def _overrides(approval: dict[str, object]) -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "active_hypotheses": [],
        "hypothesis_decisions": [],
        "change_proposals": [],
        "standing_live_change_approval": approval,
    }


def _approval() -> dict[str, object]:
    return {
        "approval_status": "standing_preapproved_for_validated_required_changes",
        "approval_evidence": "operator-approval.json",
        "approved_scope": ["verified technical and strategy repairs"],
        "excluded_scope": ["speculative unvalidated exposure increases"],
        "agent_may_apply_after_validation": True,
        "agent_reapproval_required": False,
        "automatic_live_change": False,
        "live_arming_flags_required": True,
        "validation_required": True,
        "rollback_required": True,
    }
