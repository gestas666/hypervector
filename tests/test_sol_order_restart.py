"""Pure restart tests for unresolved durable SOL order intent."""

from __future__ import annotations

from collections.abc import Mapping

import pytest


_ENTRY_ID = "0x11111111111111111111111111111111"
_STOP_ID = "0x22222222222222222222222222222222"
_TARGET_ID = "0x33333333333333333333333333333333"


def _record(
    sequence: int,
    event_type: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": f"2026-07-31T12:00:0{sequence}+00:00",
        "payload": dict(payload),
    }


def test_latest_unacknowledged_intent_is_recovered_with_original_payload() -> None:
    """Restart retains the exact operation inputs needed for reconciliation."""
    from hypervector.live.sol_order_restart import pending_order_intent

    records = [
        _record(
            1,
            "order_intent",
            {
                "operation": "entry",
                "client_order_id": _ENTRY_ID,
                "side": "long",
                "requested_notional_usd": 22.50,
                "mark_price": 73.0,
            },
        )
    ]

    pending = pending_order_intent(records)

    assert pending is not None
    assert pending.operation == "entry"
    assert pending.client_order_id == _ENTRY_ID
    assert pending.payload["side"] == "long"
    assert pending.observed_at_utc == "2026-07-31T12:00:01+00:00"


def test_matching_acknowledgement_resolves_durable_intent() -> None:
    """A completed response cannot be mistaken for restart ambiguity."""
    from hypervector.live.sol_order_restart import pending_order_intent

    records = [
        _record(
            1,
            "order_intent",
            {"operation": "entry", "client_order_id": _ENTRY_ID},
        ),
        _record(
            2,
            "order_acknowledgement",
            {
                "operation": "entry",
                "client_order_id": _ENTRY_ID,
                "accepted": True,
                "oid": 101,
            },
        ),
    ]

    assert pending_order_intent(records) is None


def test_multiple_unresolved_intents_fail_instead_of_guessing_ownership() -> None:
    """Restart refuses an impossible concurrent-mutation history."""
    from hypervector.live.sol_order_restart import (
        SolOrderRestartError,
        pending_order_intent,
    )

    records = [
        _record(
            1,
            "order_intent",
            {"operation": "entry", "client_order_id": _ENTRY_ID},
        ),
        _record(
            2,
            "order_intent",
            {"operation": "protective_stop", "client_order_id": _STOP_ID},
        ),
    ]

    with pytest.raises(SolOrderRestartError, match="multiple unresolved"):
        pending_order_intent(records)


def test_ack_for_another_client_id_does_not_resolve_pending_intent() -> None:
    """Only an acknowledgement for the exact CLOID closes the restart record."""
    from hypervector.live.sol_order_restart import pending_order_intent

    records = [
        _record(
            1,
            "order_intent",
            {"operation": "entry", "client_order_id": _ENTRY_ID},
        ),
        _record(
            2,
            "order_acknowledgement",
            {"operation": "entry", "client_order_id": _STOP_ID},
        ),
    ]

    pending = pending_order_intent(records)

    assert pending is not None
    assert pending.client_order_id == _ENTRY_ID


def test_interrupted_lifecycle_retains_acked_intent_after_pending_state() -> None:
    """An acked order still supplies recovery context until lifecycle advances."""
    from hypervector.live.sol_order_restart import interrupted_lifecycle_intent

    records = [
        _record(1, "state_transition", {"state": "ENTRY_PENDING"}),
        _record(
            2,
            "order_intent",
            {
                "operation": "entry",
                "client_order_id": _ENTRY_ID,
                "side": "long",
                "mark_price": 73.0,
            },
        ),
        _record(
            3,
            "order_acknowledgement",
            {"operation": "entry", "client_order_id": _ENTRY_ID, "oid": 101},
        ),
    ]

    interrupted = interrupted_lifecycle_intent(records)

    assert interrupted is not None
    assert interrupted.client_order_id == _ENTRY_ID
    assert interrupted.operation == "entry"


def test_target_ack_resolves_target_intent_and_target_pending_is_recoverable() -> None:
    """Restart recognizes the distinct target mutation and acknowledgement."""
    from hypervector.live.sol_order_restart import (
        interrupted_lifecycle_intent,
        pending_order_intent,
    )

    records = [
        _record(1, "state_transition", {"state": "TARGET_PENDING"}),
        _record(
            2,
            "order_intent",
            {
                "operation": "target",
                "client_order_id": _TARGET_ID,
                "position_size_signed": 0.3,
                "limit_price": 74.0,
            },
        ),
        _record(
            3,
            "target_order",
            {"operation": "target", "client_order_id": _TARGET_ID, "oid": 203},
        ),
    ]

    assert pending_order_intent(records) is None
    interrupted = interrupted_lifecycle_intent(records)
    assert interrupted is not None
    assert interrupted.operation == "target"


def test_false_target_visibility_fault_remains_recoverable() -> None:
    """Restart rechecks an acknowledged target after the known visibility fault."""
    from hypervector.live.sol_order_restart import interrupted_lifecycle_intent

    records = [
        _record(1, "state_transition", {"state": "TARGET_PENDING"}),
        _record(
            2,
            "order_intent",
            {
                "operation": "target",
                "client_order_id": _TARGET_ID,
                "position_size_signed": 0.3,
                "limit_price": 74.0,
            },
        ),
        _record(
            3,
            "target_order",
            {
                "operation": "target",
                "client_order_id": _TARGET_ID,
                "accepted": True,
                "oid": 203,
            },
        ),
        _record(
            4,
            "fault",
            {
                "reason": (
                    "target acknowledged but complete bracket is not venue-visible"
                )
            },
        ),
        _record(5, "state_transition", {"state": "FAULTED"}),
    ]

    interrupted = interrupted_lifecycle_intent(records)

    assert interrupted is not None
    assert interrupted.operation == "target"
    assert interrupted.client_order_id == _TARGET_ID
