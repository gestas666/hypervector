"""Proven cleanup terminates one lifecycle without erasing unrelated or malformed evidence."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_cleanup_evidence import pending_records
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_protective_cleanup_checkpoint import (
    CLEANUP_PHASE,
    pending_protective_cleanup,
)
from hypervector.live.asset_protective_cleanup_suffix import validate_cleanup_suffix

__all__ = ["deny_external_ports", "pending_records"]


@pytest.mark.parametrize(
    "corruption", ["completion", "missing_owner", "changed_state", "receipt_order"]
)
def test_cleanup_rejects_unproven_completion_and_missing_original_lifecycle(
    pending_records: list[dict[str, object]], corruption: str
) -> None:
    """Later completion claims and marker fields require their preceding original lifecycle."""
    records = deepcopy(pending_records)
    marker = next(row for row in records if row["payload"].get("phase") == CLEANUP_PHASE)
    index = records.index(marker)
    if corruption == "completion":
        records.append(
            {
                **records[-1],
                "event_type": "close",
                "payload": {
                    "reason": "protective_stop_remainder",
                    "verified_flat": True,
                    "owned_oids": [99999],
                },
            }
        )
    elif corruption == "missing_owner":
        records = [
            row for row in records[:index] if row["event_type"] != "state_transition"
        ] + records[index:]
    elif corruption == "changed_state":
        previous = next(
            row for row in reversed(records[:index]) if row["event_type"] == "state_transition"
        )
        previous["payload"]["state"] = "OPEN"
    else:
        marker["payload"]["completed_progress"]["fills"].reverse()
    with pytest.raises(AssetOrderRestartError):
        pending_protective_cleanup(records)


def test_recorded_completion_followed_by_flat_resolves_the_cleanup_checkpoint(
    pending_records: list[dict[str, object]],
) -> None:
    """An already finished cleanup must not become a new restart obligation."""
    records = deepcopy(pending_records)
    context = pending_protective_cleanup(records)
    assert context is not None
    body = {
        "reason": "protective_stop_remainder",
        "verified_flat": True,
        "owned_oids": sorted({fill.oid for fill in context.completed.fills}),
    }
    records.append({**records[-1], "event_type": "close", "payload": body})
    records.append(
        {
            **records[-1],
            "event_type": "state_transition",
            "payload": {"state": "FLAT", "position_size_signed": 0.0},
        }
    )
    assert pending_protective_cleanup(records) is None


@pytest.mark.parametrize(
    "case", ["owned_status", "unknown_operation", "missing_fault", "changed_fault_state"]
)
def test_cleanup_suffix_preserves_only_owned_status_and_recognized_faults(
    pending_records: list[dict[str, object]], case: str
) -> None:
    """Recovery accepts an owned status lookup while rejecting unrelated acknowledgement or fault records."""
    records = deepcopy(pending_records)
    context = pending_protective_cleanup(records)
    assert context is not None
    kind, body = (
        "order_acknowledgement",
        {
            "operation": "protective_cleanup_status",
            "oid": context.owner.stop_oid,
            "accepted": True,
            "status": "canceled",
        },
    )
    if case == "unknown_operation":
        body["operation"] = "entry"
    elif case == "missing_fault":
        kind, body = "fault", {"reason": None}
    elif case == "changed_fault_state":
        kind, body = "state_transition", {"state": "FAULTED", "last_fault": "unrelated failure"}
    records.append({**records[-1], "event_type": kind, "payload": body})
    if case == "owned_status":
        validate_cleanup_suffix(records, context)
    else:
        with pytest.raises(AssetOrderRestartError, match="contradictory"):
            validate_cleanup_suffix(records, context)


def test_racing_target_completion_without_accepted_close_survives_another_restart(
    tmp_path: Path,
) -> None:
    """A target completing during a rejected close retains exact economics without a close OID."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))

    def rejected(*args: object, **kwargs: object) -> dict[str, object]:
        replay.fill_owned_order(original.target_oid, history_delay_ms=0)
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"error": "fixture close rejected before acceptance"}]},
            },
        }

    replay._exchange.market_close.side_effect = rejected
    replay.engines["BTC"].reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
    )
    before = list(replay.mutations)
    restart(replay, "BTC")
    assert replay.mutations == [*before, "configure"]
    assert replay._exchange.market_close.call_count == 1
    assert_closed_economics(replay, "BTC")
