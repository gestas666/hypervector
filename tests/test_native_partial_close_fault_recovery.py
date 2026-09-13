"""Late fill history must remain recoverable after an acknowledged partial close faults."""

from dataclasses import replace
from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("symbol", ["BTC", "xyz:SNDK"])
@pytest.mark.parametrize("repeat", [False, True])
def test_partial_close_fill_history_can_arrive_after_repeated_restart_failure(
    tmp_path: Path, symbol: str, repeat: bool
) -> None:
    """Keep the same owned close recoverable until late fill attribution is available."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, partial_operation="close")
    asset = replay.assets[symbol]
    original = replay.enter_current(asset)
    collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(collateral, cash_usd=collateral.cash_usd / 2)
    fills = replay._visible_fills
    replay._info.user_fills.side_effect = lambda address: [
        row for row in fills(address) if row["dir"].startswith("Open")
    ]
    replay.prepare_close(symbol)
    with pytest.raises(SolLiveEngineError, match="protected exposure remains"):
        replay.engines[symbol].exit(mark_price=100, reason="late_close_fill_history")
    if repeat:
        with pytest.raises(SolLiveEngineError):
            replay.engine(asset).start()
    replay._info.user_fills.side_effect = fills
    recovered = replay.engine(asset).start()
    assert recovered.state is SolLiveState.OPEN
    assert recovered.position_size_signed == pytest.approx(original.position_size_signed / 2)
    assert recovered.opened_at_ms == original.opened_at_ms
    assert (recovered.target_oid is not None) == (original.target_oid is not None)
    assert replay.mutations.count("close") == 1
