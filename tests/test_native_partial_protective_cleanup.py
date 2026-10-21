"""Recover exact partial-stop completion when leftover target cleanup is interrupted."""

from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_order_submission import AssetCancelRecoveryError
from hypervector.live.asset_engine_contract import AssetLiveEngineError

__all__ = ["deny_external_ports"]
CLEANUP_DELAY_MS = 10_000


@pytest.mark.parametrize("failure", ["rejected", "lost_response", "delayed_visibility"])
def test_completed_partial_stop_recovers_leftover_target_cleanup_without_another_close(
    tmp_path: Path, failure: str
) -> None:
    """A confirmed close keeps exact ownership through cleanup faults and repeated restarts."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))
    original_cancel = replay._exchange.cancel.side_effect
    if failure == "rejected":
        replay._exchange.cancel.side_effect = lambda *args, **kwargs: {
            "status": "ok",
            "response": {
                "type": "cancel",
                "data": {"statuses": [{"error": "fixture cancel rejected before mutation"}]},
            },
        }
    else:
        replay.lost, replay.recovery_delay_ms = "cancel", CLEANUP_DELAY_MS
        if failure == "delayed_visibility":

            def delayed_cancel(name: str, oid: int) -> object:
                response = original_cancel(name, oid)
                replay.scheduled[oid].visible_at_ms = replay.clock.now_ms + CLEANUP_DELAY_MS
                return response

            replay.lost = None
            replay._exchange.cancel.side_effect = delayed_cancel
    with pytest.raises((AssetLiveEngineError, AssetCancelRecoveryError)):
        replay.engines["BTC"].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
        )
    assert "BTC" not in replay.account.snapshot().positions
    assert replay.mutations.count("close") == 1
    if failure != "rejected":
        for _ in range(2):
            with pytest.raises((AssetLiveEngineError, AssetCancelRecoveryError)):
                restart(replay, "BTC")
    replay.clock.advance_to(replay.clock.now_ms + CLEANUP_DELAY_MS)
    replay._exchange.cancel.side_effect = original_cancel
    replay.lost = None
    restart(replay, "BTC")
    assert replay.mutations.count("close") == 1
    assert replay.mutations.count("cancel") == 1
    assert_closed_economics(replay, "BTC")
