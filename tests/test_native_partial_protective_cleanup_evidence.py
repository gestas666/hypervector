"""Corrupted completion checkpoints and later unrelated mutations cannot authorize cleanup."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_cleanup_compound import _rejected_cancel
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_order_restart import AssetOrderRestartError
from hypervector.live.asset_protective_cleanup_checkpoint import (
    CLEANUP_PHASE,
    pending_protective_cleanup,
)
from hypervector.live.asset_protective_cleanup_suffix import validate_cleanup_suffix
from hypervector.live.asset_engine_contract import AssetLiveEngineError

__all__ = ["deny_external_ports"]


@pytest.fixture
def pending_records(tmp_path: Path) -> list[dict[str, object]]:
    """Produce a genuine native-engine completion checkpoint and rejected cleanup attempt."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))
    replay._exchange.cancel.side_effect = _rejected_cancel
    with pytest.raises(AssetLiveEngineError, match="cancel rejected"):
        replay.engines["BTC"].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
        )
    return replay.engines["BTC"]._ledger.read_all()


@pytest.mark.parametrize(
    "corruption",
    [
        "phase",
        "owner_extra",
        "entry",
        "stop",
        "target",
        "close",
        "size",
        "clock",
        "prior_credit",
        "completed_size",
        "completed_fee",
        "completed_identity",
        "completed_oid",
        "missing_receipts",
        "naive_timestamp",
        "early_timestamp",
        "missing_entry_ack",
    ],
)
def test_cleanup_checkpoint_rejects_corrupted_completion_proof(
    pending_records: list[dict[str, object]], corruption: str
) -> None:
    """Each independent owner, time and receipt corruption must be rejected before recovery."""
    records = deepcopy(pending_records)
    marker = next(row for row in records if row["payload"].get("phase") == CLEANUP_PHASE)
    body = marker["payload"]
    _corrupt(records, marker, body, corruption)
    with pytest.raises(AssetOrderRestartError):
        pending_protective_cleanup(records)


def _corrupt(
    records: list[dict[str, object]], marker: dict[str, object], body: dict[str, object], kind: str
) -> None:
    owner, progress = body["owner"], body["completed_progress"]
    owner_fields = {
        "entry": "entry_oid",
        "stop": "stop_oid",
        "target": "target_oid",
        "close": "close_oid",
        "size": "position_size_signed",
        "clock": "opened_at_ms",
    }
    fill_fields = {
        "completed_size": "size",
        "completed_fee": "fee_usd",
        "completed_identity": "trade_id",
        "completed_oid": "oid",
    }
    if kind in owner_fields:
        owner[owner_fields[kind]] += 1
    elif kind in fill_fields:
        progress["fills"][-1][fill_fields[kind]] += 1
    elif kind == "phase":
        body["phase"] = "unknown_cleanup"
    elif kind == "owner_extra":
        owner["unknown_owner_field"] = True
    elif kind == "prior_credit":
        owner["protective_progress"]["stop_exit_required"] = False
    elif kind == "missing_receipts":
        progress["fills"] = []
    elif kind == "naive_timestamp":
        marker["observed_at_utc"] = "2026-09-11T14:00:00"
    elif kind == "early_timestamp":
        marker["observed_at_utc"] = "2026-09-11T13:00:00+00:00"
    else:
        entry = next(
            row
            for row in records
            if row["event_type"] == "order_acknowledgement"
            and row["payload"].get("operation") == "entry"
        )
        entry["payload"]["accepted"] = False


@pytest.mark.parametrize(
    "kind,body",
    [
        ("order_intent", {"operation": "entry", "client_order_id": "unrelated"}),
        ("cancel_intent", {"operation": "cancel_order", "oid": 99999}),
        ("order_acknowledgement", {"operation": "cancel_residual_after_close", "oid": 99999}),
        ("fault", {"reason": "unrelated operator failure"}),
        ("state_transition", {"state": "OPEN", "position_size_signed": 1}),
    ],
)
def test_cleanup_rejects_unrelated_later_mutations_and_states(
    pending_records: list[dict[str, object]], kind: str, body: dict[str, object]
) -> None:
    """A correct completion checkpoint cannot erase later contradictory ownership evidence."""
    records = deepcopy(pending_records)
    records.append(
        {**records[-1], "sequence": len(records) + 1, "event_type": kind, "payload": body}
    )
    context = pending_protective_cleanup(records)
    assert context is not None
    with pytest.raises(AssetOrderRestartError, match="contradictory"):
        validate_cleanup_suffix(records, context)


@pytest.mark.parametrize("kind", ["entry", "exit", "changed_receipt"])
def test_completed_proof_rejects_later_owned_fill_evidence(
    pending_records: list[dict[str, object]], kind: str
) -> None:
    """New or altered owned receipts cannot disappear when current history later ages out."""
    records = deepcopy(pending_records)
    context = pending_protective_cleanup(records)
    assert context is not None
    fills = [row for row in records if row["event_type"] == "fill"]
    row = deepcopy(fills[0] if kind == "entry" else fills[-1])
    if kind == "changed_receipt":
        row["payload"]["fee_usd"] += 1
    else:
        row["payload"]["trade_id"] += 99999
    records.append({**row, "sequence": len(records) + 1})
    with pytest.raises(AssetOrderRestartError, match="contradictory"):
        validate_cleanup_suffix(records, context)


@pytest.mark.parametrize("kind", ["absent_oid", "accepted_type", "status_type"])
def test_cleanup_rejects_malformed_status_acknowledgements(
    pending_records: list[dict[str, object]], kind: str
) -> None:
    """An absent optional target is not an owned order or a valid acknowledgement identity."""
    records = deepcopy(pending_records)
    context = pending_protective_cleanup(records)
    assert context is not None
    body = {
        "operation": "protective_cleanup_status",
        "oid": context.owner.stop_oid,
        "accepted": True,
        "status": "canceled",
    }
    records = records[: context.marker_index + 1]
    if kind == "absent_oid":
        context = replace(context, owner=replace(context.owner, target_oid=None))
        body["oid"] = None
    elif kind == "accepted_type":
        body["accepted"] = "true"
    else:
        body["status"] = 1
    records.append(
        {
            **records[-1],
            "sequence": len(records) + 1,
            "event_type": "order_acknowledgement",
            "payload": body,
        }
    )
    with pytest.raises(AssetOrderRestartError, match="contradictory"):
        validate_cleanup_suffix(records, context)
