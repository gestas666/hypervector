"""Original durable receipts remain authoritative when recent venue history ages out."""

from decimal import Decimal
import json
from pathlib import Path

import pytest
from test_native_partial_protective_recovery import restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_engine_contract import AssetLiveEngineError

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("corruption", ["fee", "receipt_id", "entry_owner", "false_exit"])
def test_restart_rejects_corrupt_credit_even_after_receipt_ages_out(
    tmp_path: Path, corruption: str
) -> None:
    """A checkpoint cannot silently replace original economics or invent an exit obligation."""
    replay, original = _partial_fixture(tmp_path, "BTC", "target", False, Decimal("0.5"))
    engine = replay.engines["BTC"]
    engine.reconcile_telemetry(
        funding_start_time_ms=original.opened_at_ms,
        funding_end_time_ms=replay.clock.now_ms,
    )
    records = engine._ledger.read_all()
    state = next(
        row["payload"] for row in reversed(records) if row["event_type"] == "state_transition"
    )
    progress = state["protective_progress"]
    if corruption == "fee":
        progress["fills"][0]["fee_usd"] += 1
    elif corruption == "receipt_id":
        progress["fills"][0]["trade_id"] += 10_000
    elif corruption == "entry_owner":
        state["entry_oid"] += 10_000
    else:
        progress["stop_exit_required"] = True
    engine._ledger.path.write_text("".join(json.dumps(row) + "\n" for row in records))
    replay._info.user_fills.side_effect = lambda address: [
        row for row in replay._visible_fills(address) if row["oid"] != original.target_oid
    ]
    before = list(replay.mutations)
    with pytest.raises(AssetLiveEngineError, match="checkpoint"):
        restart(replay, "BTC")
    assert replay.mutations == before
