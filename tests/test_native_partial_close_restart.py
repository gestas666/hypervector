"""Partial close recovery must survive the same native restart boundaries as full fills."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.asset_order_submission import AssetOrderRecoveryError
from hypervector.live.asset_state import AssetLiveState

__all__ = ["deny_external_ports"]
SYMBOLS = ["BTC", "ETH", "SOL", "HYPE", "xyz:BBB", "xyz:CCC", "xyz:EEE"]


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("last_side", [False, True])
@pytest.mark.parametrize("status", ["filled", "canceled"])
def test_partial_close_status_timeout_recovers_and_closes_only_the_remainder(
    tmp_path: Path, symbol: str, last_side: bool, status: str
) -> None:
    """A delayed terminal lookup cannot strand reduced exposure or shift its hold clock."""
    replay = ScheduledEngineFixture(
        tmp_path,
        lost=None,
        partial_operation="close",
        partial_status=status,
        recovery_delay_ms=5000,
    )
    asset = replay.assets[symbol]
    original = replay.enter_current(asset, last_side=last_side)
    collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(collateral, cash_usd=collateral.cash_usd / 2)
    replay.prepare_close(symbol)
    replay.lost = "close"
    with pytest.raises(AssetOrderRecoveryError):
        replay.engines[symbol].exit(mark_price=100, reason="partial_restart_contract")
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    replay.lost = None
    engine = replay.engine(asset)
    recovered = engine.start()
    assert recovered.state is AssetLiveState.OPEN
    quantity = replay.account.snapshot().positions[symbol].quantity_signed
    assert Decimal(str(recovered.position_size_signed)) == quantity
    assert recovered.opened_at_ms == original.opened_at_ms
    assert (recovered.target_oid is not None) == (original.target_oid is not None)
    assert replay.mutations.count("close") == 1
    replay.assert_native_account_agreement()
    replay.partial_operation = None
    replay.prepare_close(symbol)
    assert engine.exit(mark_price=100, reason="remaining_close").state is AssetLiveState.FLAT
    assert not replay.account.snapshot().positions and not replay.orders
    assert replay.mutations.count("close") == 2
