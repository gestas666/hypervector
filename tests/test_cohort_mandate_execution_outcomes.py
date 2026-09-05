"""Continuous-mandate order outcome validation tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_mandate_execution_outcomes import (
    mandate_order_rejections,
)


def test_exact_current_run_submission_outcomes_replace_inference() -> None:
    """Ledger acknowledgements replace inference from action and fault counts."""
    execution = {"current_run_submission_outcomes": _summary()}

    rejections = mandate_order_rejections(execution, routing_actions=2)

    assert rejections == {
        "status": "measured",
        "count": 1,
        "routing_actions": 2,
        "observed_submission_outcomes": 3,
        "accepted_submission_outcomes": 2,
        "by_operation": _summary()["by_operation"],
        "rejection_reasons": {"insufficient margin": 1},
    }


def test_submission_outcome_contradiction_fails_closed() -> None:
    """Checkpoint summaries cannot undercount rejected acknowledgements."""
    summary = _summary()
    summary["outcomes"] = 2

    with pytest.raises(ValueError, match="submission outcome counts disagree"):
        mandate_order_rejections(
            {"current_run_submission_outcomes": summary}, routing_actions=2
        )


def _summary() -> dict[str, object]:
    return {
        "scope": "current_run",
        "status": "measured",
        "outcomes": 3,
        "accepted": 2,
        "rejected": 1,
        "source_events": {"close": 1, "order_acknowledgement": 2},
        "by_operation": {
            "entry": {
                "outcomes": 2,
                "accepted": 1,
                "rejected": 1,
                "by_status": {"error": 1, "filled": 1},
            },
            "reduce_only_close": {
                "outcomes": 1,
                "accepted": 1,
                "rejected": 0,
                "by_status": {"filled": 1},
            },
        },
        "rejection_reasons": {"insufficient margin": 1},
    }
