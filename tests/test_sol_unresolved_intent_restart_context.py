"""Exact retirement of failed startups that halted only on ambiguous unresolved intents."""

import pytest

from hypervector.live.sol_order_restart import MULTIPLE_UNRESOLVED_INTENTS
from hypervector.live.sol_unresolved_intent_restart_context import (
    records_before_unresolved_intent_startup_fault,
)

_EMPTY = {
    "entry_oid": None,
    "stop_oid": None,
    "target_oid": None,
    "close_oid": None,
    "position_size_signed": 0.0,
    "opened_at_ms": None,
    "last_fault": None,
    "execution_plan": None,
    "target_price": None,
    "protective_progress": {"fills": [], "stop_exit_required": False},
}


def _state(state: str, **values: object) -> dict[str, object]:
    return {
        "event_type": "state_transition",
        "payload": {**_EMPTY, "state": state, **values},
    }


def _row(kind: str, **payload: object) -> dict[str, object]:
    return {"event_type": kind, "payload": payload}


def _open() -> dict[str, object]:
    return _state(
        "OPEN", entry_oid=11, stop_oid=22, position_size_signed=5.84, opened_at_ms=1
    )


def _raise(client_id: str) -> dict[str, object]:
    return _row(
        "order_intent",
        operation="raise_protective_stop",
        client_order_id=client_id,
        oid=22,
    )


def _failed_startup(
    reason: str = MULTIPLE_UNRESOLVED_INTENTS,
) -> list[dict[str, object]]:
    return [
        _row("session_start", state="PREFLIGHT"),
        _state("PREFLIGHT"),
        _row("configuration_identity", symbol="xyz:EEE"),
        _row("effective_mode", state="LIVE ARMED"),
        _row("fee", maker_rate=0.0),
        _row("reconciliation", open_order_ids=[22]),
        _row("position", size_signed=5.84),
        _row("liquidation_price", value=88.86),
        _row("fault", reason=reason),
        _state("FAULTED", last_fault=reason),
    ]


def _history() -> list[dict[str, object]]:
    return [
        _open(),
        _raise("0x" + "1" * 32),
        _row("session_start", state="PREFLIGHT"),
        _state("PREFLIGHT"),
        _open(),
        _raise("0x" + "2" * 32),
    ]


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_trailing_failed_startups_are_removed_from_the_recovery_view(
    failures: int,
) -> None:
    history = _history()
    records = history + [row for _ in range(failures) for row in _failed_startup()]

    view = records_before_unresolved_intent_startup_fault(records)

    assert view == history + [_row("session_start", state="PREFLIGHT")]
    assert records[: len(view)] == view


def test_history_without_a_failed_startup_is_unchanged() -> None:
    records = _history()
    assert records_before_unresolved_intent_startup_fault(records) is records


def test_a_different_startup_fault_is_left_for_existing_paths() -> None:
    records = _history() + _failed_startup(
        "unknown venue exposure exists without local ownership"
    )
    assert records_before_unresolved_intent_startup_fault(records) is records


def test_a_later_different_startup_fault_keeps_the_whole_history() -> None:
    other = _failed_startup("unknown venue exposure exists without local ownership")
    records = _history() + _failed_startup() + other
    assert records_before_unresolved_intent_startup_fault(records) is records


def test_a_startup_killed_after_preflight_is_not_retired_on_its_own() -> None:
    records = _history() + _failed_startup()[:5]
    assert records_before_unresolved_intent_startup_fault(records) is records


@pytest.mark.parametrize(
    "later",
    [
        _raise("0x" + "3" * 32),
        _row("cancel_intent", operation="cancel_order", oid=22),
        _row("stop_order", client_order_id="0x" + "2" * 32, accepted=False, oid=None),
        _row("close", reason="stop", oid=22),
        _open(),
        _state("PREFLIGHT", stop_oid=22, position_size_signed=5.84),
        _state("FAULTED", last_fault=MULTIPLE_UNRESOLVED_INTENTS, stop_oid=22),
    ],
)
def test_any_mutation_or_ownership_after_the_failure_keeps_the_history(
    later: dict[str, object],
) -> None:
    records = _history() + _failed_startup() + [later] + _failed_startup()[-2:]
    assert records_before_unresolved_intent_startup_fault(records) is records


def test_retired_attempts_leave_only_read_only_rows_after_the_last_owned_state() -> (
    None
):
    records = _history() + _failed_startup() + _failed_startup()
    view = records_before_unresolved_intent_startup_fault(records)
    retired = records[len(view) :]
    assert {row["event_type"] for row in retired} <= {
        "state_transition",
        "configuration_identity",
        "effective_mode",
        "fee",
        "reconciliation",
        "position",
        "liquidation_price",
        "fault",
        "session_start",
    }
    assert not [row for row in retired if row["event_type"] == "order_intent"]
