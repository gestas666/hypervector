"""Cross-run candidate identity and activation tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_signal_candidates import evaluation_candidates

_DECISION_MS = 1_800_000_000_000


def test_candidates_are_deduplicated_within_each_source_run() -> None:
    """The same decision from two compatible runs remains separately auditable."""
    evaluation = _evaluation(_DECISION_MS)
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 120_000, "run-a"),
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-b"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 1_000,
            "run-a",
        ),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 2_000,
            "run-b",
        ),
    ]

    candidates, excluded, conflicts = evaluation_candidates(records)

    assert excluded == 0
    assert conflicts == 0
    assert [(row.source_run_id, row.decision_time_ms) for row in candidates] == [
        ("run-a", _DECISION_MS),
        ("run-b", _DECISION_MS),
    ]


def test_each_run_uses_its_own_activation_boundary() -> None:
    """A restarted run cannot admit a stale pre-start provider decision."""
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 120_000, "run-a"),
        _row("configuration_identity", {}, _DECISION_MS + 60_000, "run-b"),
        _row(
            "intent_routing",
            {"evaluations": [_evaluation(_DECISION_MS)]},
            _DECISION_MS + 61_000,
            "run-b",
        ),
    ]

    candidates, excluded, conflicts = evaluation_candidates(records)

    assert candidates == ()
    assert excluded == 1
    assert conflicts == 0


def test_candidate_preserves_decision_time_regime_context() -> None:
    """Forward attribution retains the backend's causal regime tuple."""
    evaluation = _evaluation(_DECISION_MS)
    evaluation["primary_regime"] = "RANGE"
    evaluation["state_1m"] = "TRANSITION"
    evaluation["state_5m"] = "RANGE"
    evaluation["context_15m"] = "TREND_UP"
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-a"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 1_000,
            "run-a",
        ),
    ]

    candidates, _, _ = evaluation_candidates(records)

    assert candidates[0].metrics == {
        "primary_regime": "RANGE",
        "state_1m": "TRANSITION",
        "state_5m": "RANGE",
        "context_15m": "TREND_UP",
    }


def test_candidate_rejects_conflicting_five_minute_state() -> None:
    """Duplicated state fields cannot silently disagree across the boundary."""
    evaluation = _evaluation(_DECISION_MS)
    evaluation["state_5m"] = "RANGE"
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    readiness["metrics"] = {"state_5m": "TREND_UP"}
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-a"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 1_000,
            "run-a",
        ),
    ]

    with pytest.raises(ValueError, match="five-minute state fields disagree"):
        evaluation_candidates(records)


def _evaluation(decision_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": 40.0,
        "side": None,
        "eligible": False,
        "readiness": {
            "side": "long",
            "blockers": ["5m_not_breakout"],
            "metrics": {},
        },
    }


def _row(
    event_type: str,
    values: dict[str, object],
    observed_ms: int,
    source_run_id: str,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": source_run_id,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "payload": values,
    }
