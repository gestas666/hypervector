"""Canceled partial entries require current owned fills before protection or adoption."""

from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_order_submission import SolOrderRecoveryError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


def test_partial_entry_waits_for_its_delayed_fill_history(tmp_path: Path) -> None:
    """Known canceled status alone does not end bounded fill-identity reconciliation."""
    replay = ScheduledEngineFixture(
        tmp_path, lost="entry", partial_operation="entry", partial_status="canceled"
    )
    original = replay.clock.now_ms
    fills = replay._visible_fills
    replay._info.user_fills.side_effect = (
        lambda address: fills(address) if replay.clock.now_ms >= original + 1000 else []
    )
    state = replay.enter_current(replay.assets["BTC"])
    assert state.state is SolLiveState.OPEN and state.opened_at_ms == original
    assert replay.clock.now_ms >= original + 1000
    assert replay.mutations.count("entry") == 1


@pytest.mark.parametrize("foreign", [False, True])
def test_unattributed_partial_entry_keeps_the_original_intent_retryable(
    tmp_path: Path, foreign: bool
) -> None:
    """No missing or foreign fills can authorize protection of unknown exposure."""
    replay = ScheduledEngineFixture(
        tmp_path, lost="entry", partial_operation="entry", partial_status="canceled"
    )
    fills = replay._visible_fills
    replay._info.user_fills.side_effect = (
        lambda address: [{**row, "oid": row["oid"] + 900} for row in fills(address)]
        if foreign
        else []
    )
    asset = replay.assets["BTC"]
    original = replay.clock.now_ms
    with pytest.raises(SolOrderRecoveryError):
        replay.enter_current(asset)
    assert not replay.orders and replay.mutations.count("entry") == 1
    replay._info.user_fills.side_effect = fills
    recovered = replay.engine(asset).start()
    assert recovered.state is SolLiveState.OPEN and recovered.opened_at_ms == original
    assert recovered.target_oid is not None and replay.mutations.count("entry") == 1


@pytest.mark.parametrize("symbol", ["BTC", "xyz:SNDK"])
def test_long_delayed_canceled_entry_restart_uses_owned_partial_fill(
    tmp_path: Path, symbol: str
) -> None:
    """Restart after status timeout protects only the partial position and original clock."""
    replay = ScheduledEngineFixture(
        tmp_path,
        lost="entry",
        partial_operation="entry",
        partial_status="canceled",
        recovery_delay_ms=5000,
    )
    original = replay.clock.now_ms
    with pytest.raises(SolOrderRecoveryError):
        replay.enter_current(replay.assets[symbol])
    replay.clock.advance_to(original + 6000)
    recovered = replay.engine(replay.assets[symbol]).start()
    assert recovered.state is SolLiveState.OPEN and recovered.opened_at_ms == original
    assert replay.mutations.count("entry") == 1
