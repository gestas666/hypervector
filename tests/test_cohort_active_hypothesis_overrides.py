"""Contracts for supplemental report-only active research hypotheses."""

from __future__ import annotations

from hypervector.research.cohort_continuous_improvement import _hypothesis_ledger
from hypervector.research.cohort_improvement_digest import (
    _apply_experiment_overrides,
)


def _active() -> dict[str, object]:
    return {
        "hypothesis_id": "pressure-persistence-v1",
        "route": "index|xyz:SP500,xyz:SPCX",
        "status": "being_tested",
        "experiment": "pressure_persistence",
        "execution_effect": "report_only",
    }


def _overrides() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
        },
        "routes": {},
        "active_hypotheses": [_active()],
        "hypothesis_decisions": [],
        "change_proposals": [],
    }


def test_digest_retains_supplemental_active_hypothesis() -> None:
    """A current subexperiment must not enter the closed-decision array."""
    _queue, summary = _apply_experiment_overrides([], _overrides())

    assert summary.get("active_hypotheses") == [_active()]


def test_continuous_ledger_merges_supplemental_active_hypothesis() -> None:
    """The continuous ledger must expose source-bound active subexperiments."""
    digest = {"research_decision_overrides": _overrides()}

    assert _hypothesis_ledger([], {}, digest, "v51") == [_active()]
