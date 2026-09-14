"""Replay SDK history, response loss and partial quantities retain separate economic clocks."""

from dataclasses import replace
from decimal import Decimal

import pytest
from test_native_replay_adapter import ADDRESS, deny_external_ports
from test_native_replay_sdk import SYMBOL, adapter, recorded_book, sdk

from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.sol_order_transport import SolOrderTransportError
from hypervector.research.native_replay_account import ReplayPosition
from hypervector.research.native_replay_depth import ExactLevel, RecordedBook
from hypervector.research.native_replay_events import FillEvent
from hypervector.research.native_replay_sdk_models import ReplaySdkTiming
from hypervector.research.native_replay_unified import IsolatedCollateral

__all__ = ["deny_external_ports"]
D = Decimal
ENTRY_ID = "0x" + "a" * 32
CLOSE_ID = "0x" + "b" * 32


def shallow_book(symbol: str, time_ms: int, step: Decimal) -> RecordedBook:
    """Supply independently bounded partial depth for this declared test scenario."""
    return replace(
        recorded_book(symbol, time_ms, step),
        bids=(ExactLevel(D("99.9"), D(".5")),),
        asks=(ExactLevel(D("100.1"), D(1)),),
    )


def proportional_test_collateral(
    before: ReplayPosition,
    after: ReplayPosition,
    old: IsolatedCollateral,
    fills: tuple[FillEvent, ...],
) -> IsolatedCollateral:
    """Supply an explicit test-only transfer assumption; do not claim native collateral parity."""
    return replace(old, cash_usd=old.cash_usd * abs(after.quantity_signed / before.quantity_signed))


def test_reusable_ports_implement_native_protocols_and_delayed_visibility() -> None:
    """Economic exposure can precede both fill history and exact order status visibility."""
    replay = sdk()
    assert isinstance(replay.info, HyperliquidInfoProtocol)
    assert isinstance(replay.exchange, HyperliquidExchangeProtocol)
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    assert replay.clock.now_ms == 1300
    assert client.reconcile().position.size_signed == 5
    assert not replay.info.user_fills(ADDRESS)
    assert replay.info.query_order_by_oid(ADDRESS, ENTRY_ID) == {"status": "unknownOid"}
    replay.advance_to(1400)
    assert len(replay.info.user_fills(ADDRESS)) == 1
    assert replay.info.query_order_by_oid(ADDRESS, 1) == {"status": "unknownOid"}
    replay.advance_to(1500)
    assert client.order_status(1).status == "filled"
    assert client.order_status_by_client_id(ENTRY_ID).oid == 1


def test_lost_response_keeps_exact_exposure_and_recoverable_client_identity() -> None:
    """A transport failure cannot turn a modeled accepted fill into an absent trade."""
    replay = sdk()
    replay.response_losses.add(ENTRY_ID)
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    with pytest.raises(SolOrderTransportError):
        client.submit_entry(
            side="short", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
        )
    assert replay.account.snapshot().positions[SYMBOL].quantity_signed == -5
    replay.advance_to(1500)
    assert client.order_status_by_client_id(ENTRY_ID).status == "filled"
    assert len(client.reconcile().fills) == 1


def test_partial_entry_and_partial_close_use_an_explicit_remaining_collateral_scenario() -> None:
    """SDK receipts, cash and remaining exposure retain exact partial execution quantities."""
    replay = sdk()
    replay.execution_book = shallow_book
    replay.partial_collateral = proportional_test_collateral
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    opening = client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    assert opening.filled_size == 1
    before = replay.collateral[SYMBOL]
    closing = client.close_position(
        position_size_signed=1, mark_price=100, client_order_id=CLOSE_ID
    )
    replay.advance_to(replay.clock.now_ms + 500)
    assert closing.filled_size == 0.5 and client.reconcile().position.size_signed == 0.5
    assert replay.collateral[SYMBOL].cash_usd == before.cash_usd / 2
    assert replay.account.snapshot().realized_gross_usd == D("-.1")
    assert client.order_status(closing.oid).status == "canceled"


def test_partial_close_without_collateral_evidence_fails_explicitly() -> None:
    """An unsupported transfer must not be converted into a success-shaped account snapshot."""
    replay = sdk()
    replay.execution_book = shallow_book
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id=ENTRY_ID
    )
    with pytest.raises(ValueError, match="explicit collateral scenario"):
        client.close_position(position_size_signed=1, mark_price=100, client_order_id=CLOSE_ID)
    with pytest.raises(ValueError, match="explicit collateral scenario"):
        replay.account_wire()


def test_no_fill_does_not_allocate_collateral_or_charge_a_fee() -> None:
    """A returned no-match response remains a canceled IOC with zero economic mutation."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    opening = client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=99, client_order_id=ENTRY_ID
    )
    replay.advance_to(1600)
    assert not opening.accepted
    assert not replay.account.snapshot().positions and not replay.collateral
    assert replay.account.snapshot().fees_usd == 0 and not replay.fill_rows
    assert replay.info.query_order_by_oid(ADDRESS, ENTRY_ID)["order"]["status"] == "canceled"


@pytest.mark.parametrize("field", range(5))
@pytest.mark.parametrize("invalid", [-1, True, 0.5])
def test_timing_scenarios_require_exact_nonnegative_milliseconds(field: int, invalid: int) -> None:
    """Booleans and submillisecond delays are not silently rounded into source evidence."""
    values = [100, 200, 300, 400, 50]
    values[field] = invalid
    with pytest.raises(ValueError):
        ReplaySdkTiming(*values)
