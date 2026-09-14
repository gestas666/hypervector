"""A newer completion checkpoint must supersede already-resolved partial-fill visibility faults."""

from decimal import Decimal
from pathlib import Path

import pytest
from test_native_partial_protective_interruptions import (
    RECEIPT_DELAY_MS,
    _delay_selected_fills,
)
from test_native_partial_protective_recovery import assert_closed_economics, restart
from test_native_protective_execution_progress import _partial_fixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("aged_out", [False, True])
def test_delayed_close_receipts_then_cleanup_rejection_recover_from_newest_proof(
    tmp_path: Path, aged_out: bool
) -> None:
    """An earlier history fault cannot override later proven closure and exact cleanup ownership."""
    replay, original = _partial_fixture(tmp_path, "BTC", "stop", False, Decimal("0.5"))
    release = replay.clock.now_ms + RECEIPT_DELAY_MS
    _delay_selected_fills(
        replay,
        delayed_oids=None,
        prior_oids={original.entry_oid, original.stop_oid, original.target_oid},
        release_ms=release,
    )
    with pytest.raises(SolLiveEngineError):
        replay.engines["BTC"].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms, funding_end_time_ms=replay.clock.now_ms
        )
    with pytest.raises(SolLiveEngineError):
        restart(replay, "BTC")
    replay.clock.advance_to(release)
    original_cancel = replay._exchange.cancel.side_effect
    replay._exchange.cancel.side_effect = _rejected_cancel
    with pytest.raises(SolLiveEngineError, match="cancel rejected"):
        restart(replay, "BTC")
    replay._exchange.cancel.side_effect = original_cancel
    if aged_out:
        replay._info.user_fills.side_effect = lambda address: []
    restart(replay, "BTC")
    assert replay.mutations.count("close") == replay.mutations.count("cancel") == 1
    assert_closed_economics(replay, "BTC")


def _rejected_cancel(name: str, oid: int) -> dict[str, object]:
    return {
        "status": "ok",
        "response": {
            "type": "cancel",
            "data": {"statuses": [{"error": "fixture cancel rejected before mutation"}]},
        },
    }
