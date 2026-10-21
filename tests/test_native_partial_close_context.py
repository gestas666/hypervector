"""Retry views must remain tied to the original exact acknowledged close."""

from copy import deepcopy

import pytest

from hypervector.live.asset_close_restart_context import (
    PARTIAL_CLOSE_UNRESOLVED,
    records_before_partial_close_fault,
)

CLIENT_ID = "0x11111111111111111111111111111111"


def history() -> list[dict[str, object]]:
    """Construct one owned close acknowledgement followed by a visibility fault."""
    ownership = {
        "entry_oid": 101,
        "stop_oid": 202,
        "position_size_signed": 0.3,
        "opened_at_ms": 1000,
    }
    return [
        {"event_type": "state_transition", "payload": {"state": "EXIT_PENDING", **ownership}},
        {
            "event_type": "order_intent",
            "observed_at_utc": "2026-09-13T00:00:00+00:00",
            "payload": {"operation": "reduce_only_close", "client_order_id": CLIENT_ID},
        },
        {
            "event_type": "close",
            "payload": {
                "operation": "reduce_only_close",
                "accepted": True,
                "status": "filled",
                "oid": 303,
                "client_order_id": CLIENT_ID,
            },
        },
        {"event_type": "fault", "payload": {"reason": PARTIAL_CLOSE_UNRESOLVED}},
        {
            "event_type": "state_transition",
            "payload": {
                "state": "FAULTED",
                **ownership,
                "close_oid": 303,
                "last_fault": PARTIAL_CLOSE_UNRESOLVED,
            },
        },
    ]


def test_retry_view_preserves_history_and_original_pending_boundary() -> None:
    """Only the recovery view stops before the first exact partial-close fault."""
    records = history()
    original = deepcopy(records)
    assert records_before_partial_close_fault(records) == records[:3]
    assert records == original


@pytest.mark.parametrize(
    "tail",
    [
        {"event_type": "order_intent", "payload": {}},
        {"event_type": "cancel_intent", "payload": {}},
        {"event_type": "close", "payload": {"partial": True}},
        {"event_type": "close", "payload": None},
        {"event_type": "fault", "payload": {"reason": "unrelated fault"}},
        {"event_type": "state_transition", "payload": {"state": "OPEN"}},
        {"event_type": "state_transition", "payload": {"state": "TARGET_PENDING"}},
        {
            "event_type": "state_transition",
            "payload": {"state": "PREFLIGHT", "position_size_signed": 1},
        },
        {"event_type": "order_acknowledgement", "payload": {}},
    ],
)
def test_new_progress_or_contradiction_prevents_replaying_old_context(
    tail: dict[str, object],
) -> None:
    """New mutation, lifecycle progress or unrelated fault must not be hidden by a retry view."""
    records = [*history(), tail]
    assert records_before_partial_close_fault(records) is records


@pytest.mark.parametrize(
    "change",
    [
        {"accepted": False},
        {"oid": None},
        {"oid": True},
        {"status": "rejected"},
        {"client_order_id": "0x22222222222222222222222222222222"},
        {"operation": "entry"},
    ],
)
def test_invalid_close_acknowledgement_cannot_authorize_retry(change: dict[str, object]) -> None:
    """The original exact close acknowledgement remains a required provenance boundary."""
    records = history()
    records[2]["payload"].update(change)
    assert records_before_partial_close_fault(records) is records


@pytest.mark.parametrize(
    "change",
    [
        {"stop_oid": 999},
        {"close_oid": 999},
        {"position_size_signed": -0.3},
        {"opened_at_ms": 2000},
        {"last_fault": "unrelated fault"},
    ],
)
def test_faulted_state_must_retain_original_close_ownership(change: dict[str, object]) -> None:
    """A mismatched saved position or order cannot inherit the old recovery authority."""
    records = history()
    records[-1]["payload"].update(change)
    assert records_before_partial_close_fault(records) is records


def test_partial_fault_without_an_exact_pending_close_is_not_rewritten() -> None:
    """A matching error message cannot substitute for a unique original close intent/ack."""
    records = history()
    records[1]["payload"]["operation"] = "entry"
    assert records_before_partial_close_fault(records) is records
    records = history()
    records.insert(3, deepcopy(records[2]))
    assert records_before_partial_close_fault(records) is records
