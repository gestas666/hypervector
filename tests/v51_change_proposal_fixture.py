"""Shared complete report-only v51 change-proposal fixture."""

from __future__ import annotations


def proposal() -> dict[str, object]:
    """Return one complete pending technical-change proposal."""
    return {
        "proposal_id": "freshness-v1",
        "recommendation": "recheck entry freshness immediately before submission",
        "why_now": "live timing reached the configured entry-age boundary",
        "evidence_reviewed": ["freshness-evidence.json"],
        "observed_problem_or_opportunity": "poll-time freshness can expire later",
        "applicable_market_regime": "all regimes",
        "alternatives_considered": ["no action", "increase delay", "faster polling"],
        "proposed_live_change": "add a shared pre-submission technical check",
        "expected_upside": "prevent stale automatic entries",
        "main_risks_and_failure_modes": ["false withholding from clock defects"],
        "validation_completed": ["focused TDD", "runner regression suite"],
        "validation_still_required": ["flat-boundary restart acceptance"],
        "success_metrics": ["zero automatic submissions beyond route age cap"],
        "failure_or_rollback_triggers": ["fresh entries are incorrectly withheld"],
        "confidence_level": "high",
        "explicit_approval_requested": True,
        "approval_status": "pending_human_approval",
        "execution_effect": "proposal_only",
        "automatic_live_change": False,
    }


def overrides(value: dict[str, object]) -> dict[str, object]:
    """Wrap one proposal in an execution-incapable override contract."""
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "change_proposals": [value],
    }
