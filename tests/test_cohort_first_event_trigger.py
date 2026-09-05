"""Contracts for source-bound first-event improvement triggers."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_first_event_trigger import (
    build_first_event_observations,
)


def test_zero_delta_remains_awaiting_first_eligible_event() -> None:
    """A quiet prefix must remain observable without inventing progress."""
    observations = build_first_event_observations(_audit(), [_hypothesis()])

    assert observations == [
        {
            "hypothesis_id": "first-event-v1",
            "status": "awaiting_first_eligible_event",
            "baseline_identity_matches": True,
            "baseline_counters": _counters(),
            "current_counters": _counters(),
            "counter_deltas": _counters(),
            "requires_immediate_audit": False,
            "technical_escalation_required": False,
            "technical_escalations": [],
            "execution_effect": "report_only",
            "automatic_live_change": False,
        }
    ]


def test_accounted_eligible_event_triggers_immediate_audit() -> None:
    """An eligible intent with one routing outcome must trigger review."""
    audit = _audit(eligible=1, intents=1, actions=1)

    observation = build_first_event_observations(audit, [_hypothesis()])[0]

    assert observation["status"] == "eligible_outcome_observed"
    assert observation["counter_deltas"]["eligible_evaluations"] == 1
    assert observation["counter_deltas"]["strategy_intents"] == 1
    assert observation["counter_deltas"]["actions"] == 1
    assert observation["requires_immediate_audit"] is True
    assert observation["technical_escalation_required"] is False


def test_preactivation_readiness_seed_does_not_trigger_an_event() -> None:
    """Provider readiness annotations must not become causal eligibility."""
    audit = _audit(readiness_eligible=1)

    observation = build_first_event_observations(audit, [_hypothesis()])[0]

    assert observation["status"] == "awaiting_first_eligible_event"
    assert observation["current_counters"]["eligible_evaluations"] == 0


def test_unaccounted_eligible_event_is_a_technical_escalation() -> None:
    """An eligible decision may not disappear before intent attribution."""
    observation = build_first_event_observations(_audit(eligible=1), [_hypothesis()])[0]

    assert observation["status"] == "technical_escalation_required"
    assert observation["technical_escalations"] == [
        "eligible_evaluation_without_strategy_intent"
    ]
    assert observation["technical_escalation_required"] is True


def test_foreign_run_baseline_is_explicitly_unavailable() -> None:
    """A restart cannot silently compare a new run with an old prefix."""
    hypothesis = _hypothesis()
    hypothesis["baseline_identity"]["run_id"] = "old-run"

    observation = build_first_event_observations(_audit(), [hypothesis])[0]

    assert observation["status"] == "baseline_identity_mismatch"
    assert observation["baseline_identity_matches"] is False
    assert observation["requires_immediate_audit"] is True
    assert observation["technical_escalation_required"] is True


def test_monotonic_counter_regression_fails_closed() -> None:
    """The current prefix cannot contain fewer events than its baseline."""
    hypothesis = _hypothesis()
    hypothesis["baseline_counters"]["eligible_evaluations"] = 2

    with pytest.raises(ValueError, match="regressed below its baseline"):
        build_first_event_observations(_audit(eligible=1), [hypothesis])


def _hypothesis() -> dict[str, object]:
    return {
        "hypothesis_id": "first-event-v1",
        "status": "being_tested",
        "execution_effect": "report_only",
        "decision_source": "decision.json",
        "evidence_baseline": "baseline.json",
        "baseline_identity": {
            "run_id": "run-1",
            "profile_id": "profile-1",
            "profile_fingerprint": "a" * 64,
        },
        "baseline_counters": _counters(),
    }


def _counters() -> dict[str, int]:
    return {
        "eligible_evaluations": 0,
        "strategy_intents": 0,
        "actions": 0,
        "withheld": 0,
        "fills": 0,
        "open_lifecycles": 0,
        "closed_trades": 0,
    }


def _audit(
    *,
    eligible: int = 0,
    readiness_eligible: int | None = None,
    intents: int = 0,
    actions: int = 0,
) -> dict[str, object]:
    readiness_count = eligible if readiness_eligible is None else readiness_eligible
    return {
        "run": {
            "run_id": "run-1",
            "profile_id": "profile-1",
            "profile_fingerprint": "a" * 64,
        },
        "readiness": {
            "by_provider_symbol": {"route|BTC": {"eligible": readiness_count}}
        },
        "routing": {
            "strategy_intents": intents,
            "actions": actions,
            "withheld": 0,
            "entry_age_diagnostics": {"eligible_evaluations": eligible},
        },
        "execution": {
            "fills": 0,
            "closed_trades": 0,
            "by_asset": {"BTC": {"open_lifecycles": 0}},
        },
    }
