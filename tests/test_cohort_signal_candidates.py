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


def test_restart_readiness_seeds_are_not_forward_candidates() -> None:
    """Repeated startup annotations cannot enter or break forward economics."""
    first = _evaluation(_DECISION_MS)
    second = _evaluation(_DECISION_MS)
    first["backend_non_action_reason"] = "pre_activation_readiness_seed"
    second["backend_non_action_reason"] = "pre_activation_readiness_seed"
    second["readiness"] = {
        "side": "long",
        "blockers": ["restart_readiness_changed"],
        "metrics": {},
    }
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-a"),
        _row("intent_routing", {"evaluations": [first]}, _DECISION_MS + 1_000, "run-a"),
        _row(
            "intent_routing", {"evaluations": [second]}, _DECISION_MS + 2_000, "run-a"
        ),
    ]

    candidates, excluded, conflicts = evaluation_candidates(records)

    assert candidates == ()
    assert excluded == 0
    assert conflicts == 0


def test_conflicting_real_provider_evaluations_still_fail_closed() -> None:
    """Changing a genuine duplicate decision remains an evidence conflict."""
    first = _evaluation(_DECISION_MS)
    second = _evaluation(_DECISION_MS)
    second["eligible"] = True
    second["side"] = "long"
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-a"),
        _row("intent_routing", {"evaluations": [first]}, _DECISION_MS + 1_000, "run-a"),
        _row(
            "intent_routing", {"evaluations": [second]}, _DECISION_MS + 2_000, "run-a"
        ),
    ]

    with pytest.raises(ValueError, match="conflicting duplicate provider evaluation"):
        evaluation_candidates(records)


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


def test_technical_unavailability_is_not_a_signal_candidate() -> None:
    """Receipt-time outage telemetry cannot enter forward-signal economics."""
    evaluation = _evaluation(_DECISION_MS + 1_234)
    evaluation.update(
        {
            "decision_action": "technical_unavailable",
            "reason": "observer_status_stale",
            "backend_non_action_reason": "observer_status_stale",
            "readiness": {
                "side": None,
                "blockers": ["observer_status_stale"],
                "metrics": {"technical_availability": "unavailable"},
            },
        }
    )
    records = [
        _row("configuration_identity", {}, _DECISION_MS - 60_000, "run-a"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 2_000,
            "run-a",
        ),
    ]

    candidates, excluded, conflicts = evaluation_candidates(records)

    assert candidates == ()
    assert excluded == 0
    assert conflicts == 0


def test_single_configured_direction_attributes_null_readiness_side() -> None:
    """A one-sided provider supplies an unambiguous counterfactual direction."""
    evaluation = _null_side_evaluation("test_long_only_1m", "BTC")
    identity = _identity_provider("test_long_only_1m", "BTC", ["long"])
    records = [
        _row("configuration_identity", identity, _DECISION_MS - 60_000, "run-a"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 1_000,
            "run-a",
        ),
    ]

    candidates, _, conflicts = evaluation_candidates(records)

    assert candidates[0].side == "long"
    assert candidates[0].side_source == "single_configured_direction"
    assert conflicts == 0


def test_bidirectional_provider_does_not_invent_null_readiness_side() -> None:
    """Two configured directions remain ambiguous without provider-native side."""
    evaluation = _null_side_evaluation("hype_both", "HYPE")
    identity = _identity_provider("hype_both", "HYPE", ["long", "short"])
    records = [
        _row("configuration_identity", identity, _DECISION_MS - 60_000, "run-a"),
        _row(
            "intent_routing",
            {"evaluations": [evaluation]},
            _DECISION_MS + 1_000,
            "run-a",
        ),
    ]

    candidates, _, conflicts = evaluation_candidates(records)

    assert candidates[0].side is None
    assert candidates[0].side_source == "unavailable"
    assert conflicts == 0


def _evaluation(decision_ms: int) -> dict[str, object]:
    return {
        "strategy_id": "test_fade_1m",
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


def _null_side_evaluation(strategy_id: str, symbol: str) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "decision_time_ms": _DECISION_MS,
        "reference_price": 100.0,
        "side": None,
        "eligible": False,
        "readiness": {"side": None, "blockers": ["trigger_absent"], "metrics": {}},
    }


def _identity_provider(
    strategy_id: str, symbol: str, sides: list[str]
) -> dict[str, object]:
    return {
        "providers": [
            {
                "strategy_id": strategy_id,
                "symbols": [symbol],
                "sides": sides,
                "execution_side_overrides": {},
            }
        ]
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
