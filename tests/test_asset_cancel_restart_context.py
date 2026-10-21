"""Only an exact owned cancellation timeout may recover its interrupted exit."""

from copy import deepcopy

import pytest

from hypervector.live.asset_cancel_restart_context import records_before_cancel_fault
from hypervector.live.asset_order_restart import AssetOrderRestartError


def source(*, target: bool = False, stopped: bool = False) -> list[dict[str, object]]:
    """Prescribe an owned exit and its exact cancellation-failure boundary."""
    oid = 103 if target else 102
    reason = f"cancel remains ambiguous after exact oid lookup: {oid}"
    rows = [
        {
            "event_type": "state_transition",
            "payload": {
                "state": "EXIT_PENDING",
                "entry_oid": 101,
                "stop_oid": 102,
                "target_oid": 103 if target else None,
                "target_price": 110 if target else None,
                "position_size_signed": 1,
                "opened_at_ms": 1000,
            },
        },
        {"event_type": "cancel_intent", "payload": {"operation": "cancel_order", "oid": oid}},
        {"event_type": "fault", "payload": {"reason": reason}},
        {"event_type": "state_transition", "payload": {"state": "FAULTED", "last_fault": reason}},
    ]
    if stopped:
        rows.append({"event_type": "state_transition", "payload": {"state": "STOPPED"}})
    return rows


@pytest.mark.parametrize("target", [False, True])
@pytest.mark.parametrize("stopped", [False, True])
def test_cancel_recovery_uses_verified_exit_context_without_rewriting_history(
    target: bool, stopped: bool
) -> None:
    """The persisted failure remains intact; only recovery's context view is bounded."""
    rows = source(target=target, stopped=stopped)
    prior = deepcopy(rows)
    assert records_before_cancel_fault(rows) == rows[:3]
    assert rows == prior


@pytest.mark.parametrize("case", ["empty", "open", "other_fault", "no_state"])
def test_unrelated_history_does_not_acquire_cancel_recovery_authority(case: str) -> None:
    """Ordinary states and unrelated faults retain existing startup validation."""
    rows = source()
    if case == "empty":
        rows = []
    elif case == "open":
        rows[-1]["payload"] = {"state": "OPEN"}
    elif case == "no_state":
        rows = [rows[1]]
    else:
        rows[-1]["payload"] = {"state": "FAULTED", "last_fault": "unrelated fault"}
    assert records_before_cancel_fault(rows) is rows


@pytest.mark.parametrize(
    "case",
    [
        "missing_cancel",
        "wrong_oid",
        "foreign_oid",
        "wrong_operation",
        "wrong_state",
        "wrong_fault",
        "missing_fault",
        "ack_after_cancel",
        "mutation_after_fault",
        "invalid_state",
        "invalid_cancel",
    ],
)
def test_corrupt_or_contradictory_cancellation_evidence_is_rejected(case: str) -> None:
    """A reason string alone cannot bypass ownership or consume a different lifecycle."""
    rows = source()
    if case == "missing_cancel":
        rows.pop(1)
    elif case == "wrong_oid":
        rows[1]["payload"]["oid"] = 104
    elif case == "foreign_oid":
        rows[0]["payload"]["stop_oid"] = 104
    elif case == "wrong_operation":
        rows[1]["payload"]["operation"] = "cancel_all"
    elif case == "wrong_state":
        rows[0]["payload"]["state"] = "OPEN"
    elif case == "wrong_fault":
        rows[2]["payload"]["reason"] = "other fault"
    elif case == "missing_fault":
        rows.pop(2)
    elif case == "ack_after_cancel":
        rows.insert(2, {"event_type": "order_acknowledgement", "payload": {"oid": 102}})
    elif case == "mutation_after_fault":
        rows.append({"event_type": "order_intent", "payload": {"operation": "entry"}})
    elif case == "invalid_state":
        rows[0]["payload"] = None
    else:
        rows[1]["payload"] = None
    with pytest.raises(AssetOrderRestartError):
        records_before_cancel_fault(rows)


def test_cancel_fault_without_any_preceding_cancel_or_state_is_rejected() -> None:
    """A standalone timeout message supplies no ownership context."""
    with pytest.raises(AssetOrderRestartError):
        records_before_cancel_fault(source()[2:])
