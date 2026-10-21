"""Rejected receipts cannot restore a stale position after observed execution."""

from dataclasses import replace
from pathlib import Path

import pytest
from native_replay_scheduled_fixture import ScheduledEngineFixture
from test_native_replay_adapter import deny_external_ports

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_order_submission import SolOrderRecoveryError
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_state import SolLiveState

__all__ = ["deny_external_ports"]


def contradictory_close(
    replay: ScheduledEngineFixture, symbol: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Let the synthetic venue execute before returning a contradictory rejection."""
    adapter = replay.adapters[symbol]
    submit = adapter.close_position

    def rejected(
        *, position_size_signed: float, mark_price: float, client_order_id: str | None = None
    ) -> HyperliquidOrderAck:
        ack = submit(
            position_size_signed=position_size_signed,
            mark_price=mark_price,
            client_order_id=client_order_id,
        )
        return replace(
            ack, accepted=False, status="canceled", error="synthetic contradictory rejection"
        )

    monkeypatch.setattr(adapter, "close_position", rejected)


@pytest.mark.parametrize("symbol", ["BTC", "xyz:CCC"])
def test_rejected_receipt_with_reduced_exposure_faults_before_new_mutation(
    tmp_path: Path, symbol: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected status cannot hide a changed position or authorize a stale target."""
    replay = ScheduledEngineFixture(tmp_path, lost=None, partial_operation="close")
    original = replay.enter_current(replay.assets[symbol])
    collateral = replay.collateral[symbol]
    replay.partial_close_collateral[symbol] = replace(collateral, cash_usd=collateral.cash_usd / 2)
    replay.prepare_close(symbol)
    contradictory_close(replay, symbol, monkeypatch)
    targets = replay.mutations.count("target")
    with pytest.raises(SolLiveEngineError, match="rejected close changed position"):
        replay.engines[symbol].exit(mark_price=100, reason="contradiction")
    assert replay.engines[symbol].snapshot.state is SolLiveState.FAULTED
    assert replay.mutations.count("target") == targets
    assert replay.mutations.count("close") == 1
    assert original.stop_oid in replay.orders


def test_partial_close_replacement_target_response_loss_recovers_without_duplicate(
    tmp_path: Path,
) -> None:
    """An accepted replacement target survives timeout without repeating the close."""
    replay = ScheduledEngineFixture(
        tmp_path, lost=None, partial_operation="close", recovery_delay_ms=5000
    )
    asset = replay.assets["BTC"]
    original = replay.enter_current(asset)
    collateral = replay.collateral[asset.symbol]
    replay.partial_close_collateral[asset.symbol] = replace(
        collateral, cash_usd=collateral.cash_usd / 2
    )
    replay.prepare_close(asset.symbol)
    replay.lost = "target"
    with pytest.raises(SolOrderRecoveryError):
        replay.engines[asset.symbol].exit(mark_price=100, reason="partial_target_loss")
    targets = replay.mutations.count("target")
    replay.clock.advance_to(replay.clock.now_ms + 6000)
    replay.lost = None
    recovered = replay.engine(asset).start()
    assert recovered.state is SolLiveState.OPEN
    assert recovered.opened_at_ms == original.opened_at_ms
    assert recovered.position_size_signed == pytest.approx(
        float(replay.account.snapshot().positions[asset.symbol].quantity_signed)
    )
    assert replay.mutations.count("close") == 1
    assert replay.mutations.count("target") == targets
    replay.assert_native_account_agreement()
