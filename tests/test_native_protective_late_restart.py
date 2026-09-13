"""Delayed protective history must preserve ownership through repeated restarts."""

from pathlib import Path

import pytest
from native_replay_protective_fixture import ProtectiveEngineFixture
from test_native_protective_observation import assert_current_flat_ledger, assert_exact_cash
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]
CASES = [
    (symbol, "stop")
    for symbol in ("BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL")
]
CASES.append(("BTC", "target"))


@pytest.mark.parametrize("symbol,order_kind", CASES)
@pytest.mark.parametrize("last_side", [False, True])
def test_late_protective_history_recovers_after_repeated_startup_failures(
    tmp_path: Path, symbol: str, order_kind: str, last_side: bool
) -> None:
    """Missing history faults; exact late receipts then close the original lifecycle once."""
    replay = ProtectiveEngineFixture(tmp_path)
    original = replay.enter_current(replay.assets[symbol], last_side=last_side)
    oid = original.stop_oid if order_kind == "stop" else original.target_oid
    assert oid is not None
    replay.fill_owned_order(oid, history_delay_ms=10000)
    before_mutations = tuple(replay.mutations)
    with pytest.raises(SolLiveEngineError):
        replay.engines[symbol].reconcile_telemetry(
            funding_start_time_ms=original.opened_at_ms,
            funding_end_time_ms=replay.clock.now_ms,
        )
    for _ in range(2):
        with pytest.raises(SolLiveEngineError):
            replay.engine(replay.assets[symbol]).start()
        assert tuple(replay.mutations) == before_mutations
    replay.clock.advance_to(replay.clock.now_ms + 10000)
    restarted = replay.engine(replay.assets[symbol])
    assert restarted.start().state is SolLiveState.FLAT
    assert not replay.orders and not replay.account.snapshot().positions
    assert replay.mutations.count("close") == 0
    assert replay.mutations.count("entry") == 1
    assert_exact_cash(replay)
    assert_current_flat_ledger(replay, symbol)
    after_mutations = tuple(replay.mutations)
    assert replay.engine(replay.assets[symbol]).start().state is SolLiveState.FLAT
    assert tuple(replay.mutations) == (*after_mutations, "configure")
    assert_current_flat_ledger(replay, symbol)
