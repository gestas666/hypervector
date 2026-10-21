"""Partial IOC lifecycle requirements with explicit synthetic collateral/status inputs."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]
D = Decimal


@pytest.mark.parametrize("status", ["filled", "canceled"])
@pytest.mark.parametrize("lost", [None, "entry"])
def test_partial_entry_preserves_owned_exposure_and_configured_protection(
    tmp_path: Path, status: str, lost: str | None
) -> None:
    """An exact owned fill must be protected even if its unfilled remainder canceled."""
    replay = ScheduledEngineFixture(
        tmp_path, lost=lost, partial_operation="entry", partial_status=status
    )
    for asset in replay.config.assets:
        state = replay.enter_current(asset)
        position = replay.account.snapshot().positions[asset.symbol]
        assert state.state is SolLiveState.OPEN
        assert D(str(state.position_size_signed)) == position.quantity_signed
        assert state.opened_at_ms == position.decision_time_ms
        assert abs(position.quantity_signed) < replay.entry_requests[-1][1]
        stop = replay.orders[state.stop_oid]
        assert D(str(stop["sz"])) == abs(position.quantity_signed)
        assert state.execution_plan is not None
        assert (state.target_oid is not None) == (state.execution_plan.target_policy != "none")
        replay.assert_native_account_agreement()
    assert replay.mutations.count("entry") == 7


@pytest.mark.parametrize("symbol", ["xyz:CCC", "BTC"])
@pytest.mark.parametrize("lost", [None, "close"])
@pytest.mark.parametrize("status", ["filled", "canceled"])
def test_partial_close_remains_recoverable_with_original_clock_and_protection(
    tmp_path: Path, symbol: str, lost: str | None, status: str
) -> None:
    """One partial close must not strand an owned remainder or discard its target policy."""
    replay = ScheduledEngineFixture(
        tmp_path, lost=None, partial_operation="close", partial_status=status
    )
    asset = replay.assets[symbol]
    original = replay.enter_current(asset)
    prior_collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(
        prior_collateral, cash_usd=prior_collateral.cash_usd / 2
    )
    replay.prepare_close(symbol)
    replay.lost = lost
    state = replay.engines[symbol].exit(mark_price=100, reason="partial_close_contract")
    position = replay.account.snapshot().positions[symbol]
    assert state.state is SolLiveState.OPEN
    assert D(str(state.position_size_signed)) == position.quantity_signed
    assert state.opened_at_ms == original.opened_at_ms == position.decision_time_ms
    stop = replay.orders[state.stop_oid]
    assert stop["reduceOnly"] and stop["isTrigger"]
    assert D(str(stop["sz"])) >= abs(position.quantity_signed)
    assert (state.target_oid is not None) == (original.target_oid is not None)
    assert replay.mutations.count("close") == 1
    replay.lost = None
    assert replay.engine(asset).start().state is SolLiveState.OPEN
    replay.assert_native_account_agreement()
