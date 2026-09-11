"""Only exact, consistent non-submission records can resolve entry intent."""

from copy import deepcopy

import pytest
from test_sol_order_restart import _ENTRY_ID, _STOP_ID, _record

from hypervector.live.sol_order_restart import (
    SolOrderRestartError,
    interrupted_lifecycle_intent,
    pending_order_intent,
)


def unsent_records() -> list[dict[str, object]]:
    """Return a pending entry followed by its exact local expiry outcome."""
    return [
        _record(1, "state_transition", {"state": "ENTRY_PENDING"}),
        _record(
            2,
            "order_intent",
            {
                "operation": "entry",
                "client_order_id": _ENTRY_ID,
                "entry_deadline": {"decision_time_ms": 1_000, "limit_ms": 30_000},
            },
        ),
        _record(
            3,
            "entry_not_submitted",
            {
                "operation": "entry",
                "client_order_id": _ENTRY_ID,
                "submitted": False,
                "reason": "stale_before_submission",
                "decision_time_ms": 1_000,
                "submission_observed_at_ms": 31_001,
                "submission_age_ms": 30_001,
                "submission_limit_ms": 30_000,
                "submission_boundary": "adapter_dispatch",
            },
        ),
    ]


def test_exact_unsent_entry_is_resolved_before_flat_state_write() -> None:
    """A durable no-dispatch record resolves both restart selectors."""
    assert pending_order_intent(unsent_records()) is None
    assert interrupted_lifecycle_intent(unsent_records()) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("client_order_id", _STOP_ID),
        ("client_order_id", []),
        ("operation", "protective_stop"),
        ("submitted", True),
        ("submitted", 0),
        ("reason", "unknown"),
        ("submission_boundary", "engine_admission"),
        ("submission_boundary", "venue_fill"),
        ("submission_boundary", []),
        ("submission_age_ms", 30_000),
        ("submission_age_ms", True),
        ("submission_limit_ms", 29_999),
        ("submission_limit_ms", 0),
        ("submission_limit_ms", -1),
        ("decision_time_ms", 999),
        ("decision_time_ms", -1),
        ("submission_observed_at_ms", 31_000),
        ("oid", 123),
    ],
)
def test_corrupted_unsent_evidence_is_rejected(field: str, value: object) -> None:
    """Corrupt markers cannot erase durable venue-ownership evidence."""
    records = unsent_records()
    records[-1]["payload"][field] = value
    with pytest.raises(SolOrderRestartError):
        pending_order_intent(records)


@pytest.mark.parametrize("field", ["decision_time_ms", "limit_ms"])
@pytest.mark.parametrize("value", [True, None, "30000", 30_000.0])
def test_persisted_deadline_contract_requires_integer_fields(
    field: str, value: object
) -> None:
    """A marker cannot supply missing or invalid policy evidence after a crash."""
    records = unsent_records()
    records[1]["payload"]["entry_deadline"][field] = value
    with pytest.raises(SolOrderRestartError, match="persisted deadline"):
        pending_order_intent(records)


@pytest.mark.parametrize(
    "variant",
    [
        "before_intent",
        "after_ack",
        "later_ack",
        "duplicate",
        "reused_id",
        "missing_contract",
        "non_entry",
    ],
)
def test_contradictory_unsent_history_is_rejected(variant: str) -> None:
    """Ordering and ownership contradictions remain explicit recovery faults."""
    records = unsent_records()
    ack = _record(4, "order_acknowledgement", {"client_order_id": _ENTRY_ID})
    if variant == "before_intent":
        records[1], records[2] = records[2], records[1]
    elif variant == "after_ack":
        records.insert(2, ack)
    elif variant == "later_ack":
        records.append(ack)
    elif variant == "duplicate":
        records.append(deepcopy(records[-1]))
    elif variant == "reused_id":
        records.append(deepcopy(records[1]))
    elif variant == "missing_contract":
        records[1]["payload"].pop("entry_deadline")
    else:
        records[1]["payload"]["operation"] = "protective_stop"
    with pytest.raises(SolOrderRestartError):
        pending_order_intent(records)
