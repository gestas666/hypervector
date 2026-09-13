"""Exact intent ownership and decision-clock integrity during entry restart."""

from dataclasses import replace

import pytest

from hypervector.live.sol_order_restart import (
    PendingSolOrderIntent,
    SolOrderRestartError,
)
from hypervector.live.sol_order_restart_context import (
    execution_plan_for_intent,
    pending_entry_opened_at_ms,
)

CLIENT_ID = "0x11111111111111111111111111111111"


def intent(payload: dict[str, object]) -> PendingSolOrderIntent:
    """Build a synthetic durable intent with explicit clock provenance."""
    return PendingSolOrderIntent("entry", CLIENT_ID, "2026-09-11T14:00:00+00:00", payload)


def records() -> list[dict[str, object]]:
    """Retain the original ENTRY_PENDING before a later ambiguity fault."""
    return [
        {
            "event_type": "state_transition",
            "payload": {"state": "ENTRY_PENDING", "execution_plan": None},
        },
        {"event_type": "order_intent", "payload": {"client_order_id": CLIENT_ID}},
        {"event_type": "state_transition", "payload": {"state": "FAULTED"}},
    ]


def test_exact_intent_selects_preceding_plan_despite_a_later_fault() -> None:
    """The fault is not substituted for the state bound to the durable identity."""
    assert execution_plan_for_intent(records(), "ENTRY_PENDING", CLIENT_ID) is None


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "wrong_state", "bad_state", "bad_intent", "bad_plan", "no_state"],
)
def test_invalid_entry_plan_context_is_not_recovered(mutation: str) -> None:
    """Absent, conflicting and malformed ownership must fail before protection."""
    source = records()
    if mutation == "missing":
        source.pop(1)
    elif mutation == "duplicate":
        source.insert(2, source[1])
    elif mutation == "wrong_state":
        source[0]["payload"] = {"state": "OPEN"}
    elif mutation == "bad_state":
        source[0]["payload"] = None
    elif mutation == "bad_intent":
        source[1]["payload"] = None
    elif mutation == "bad_plan":
        source[0]["payload"] = {"state": "ENTRY_PENDING", "execution_plan": {"invalid": True}}
    else:
        source.pop(0)
    with pytest.raises(SolOrderRestartError):
        execution_plan_for_intent(source, "ENTRY_PENDING", CLIENT_ID)


@pytest.mark.parametrize("decision", [0, 1000, 1200])
def test_pending_entry_preserves_persisted_decision_instead_of_status_time(decision: int) -> None:
    """The recovered hold starts at its original decision, including exact equality."""
    pending = intent({"entry_deadline": {"decision_time_ms": decision, "limit_ms": 30000}})
    assert pending_entry_opened_at_ms(pending, 1200) == decision


def test_legacy_intent_without_decision_keeps_explicit_venue_clock_compatibility() -> None:
    """Missing legacy data does not pretend that a decision timestamp was recorded."""
    assert pending_entry_opened_at_ms(intent({}), 1200) == 1200


@pytest.mark.parametrize(
    "deadline",
    [
        None,
        [],
        {},
        {"decision_time_ms": True, "limit_ms": 1},
        {"decision_time_ms": -1, "limit_ms": 1},
        {"decision_time_ms": 1.5, "limit_ms": 1},
        {"decision_time_ms": 1201, "limit_ms": 1},
        {"decision_time_ms": 1, "limit_ms": 0},
        {"decision_time_ms": 1, "limit_ms": True},
        {"decision_time_ms": 1, "limit_ms": -1},
    ],
)
def test_present_but_invalid_deadline_cannot_fall_back_to_venue_time(deadline: object) -> None:
    """Corrupt explicit provenance cannot silently extend or replace the hold clock."""
    with pytest.raises(SolOrderRestartError):
        pending_entry_opened_at_ms(intent({"entry_deadline": deadline}), 1200)


@pytest.mark.parametrize("timestamp", [True, -1, 1.5, None])
def test_invalid_venue_timestamp_is_rejected(timestamp: object) -> None:
    """Even a legacy fallback requires valid integer-millisecond evidence."""
    with pytest.raises(SolOrderRestartError):
        pending_entry_opened_at_ms(intent({}), timestamp)


def test_other_operation_cannot_be_reinterpreted_as_entry_clock() -> None:
    """The helper refuses a different lifecycle operation."""
    with pytest.raises(SolOrderRestartError):
        pending_entry_opened_at_ms(replace(intent({}), operation="target"), 1200)
