"""Integrated coordinator-to-event-port shadow controller tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.hypervelocity_shadow_controller import (
    HypervelocityShadowController,
)
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.strategies.hypervelocity_runtime import RuntimeMarketState

BASE_MS = 1_785_103_200_000


def iso(offset_ms: int) -> str:
    """Return a deterministic UTC event timestamp."""
    return datetime.fromtimestamp((BASE_MS + offset_ms) / 1_000, tz=UTC).isoformat()


def l2(
    offset_ms: int,
    *,
    bid_size: float = 0.001,
    bid: float = 64_500.0,
    ask: float = 64_501.0,
) -> L2SnapshotEvent:
    """Return one complete BTC book snapshot."""
    exchange_ms = BASE_MS + offset_ms
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        bids=(BookLevel(bid, bid_size, 1),),
        asks=(BookLevel(ask, 0.5, 1),),
    )


def trade(offset_ms: int, *, size: float, trade_id: int) -> PublicTradeEvent:
    """Return one sell-aggressor public trade at the resting bid."""
    exchange_ms = BASE_MS + offset_ms
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side="sell",
        price=64_500.0,
        size=size,
        transaction_hash=f"0x{trade_id}",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        trade_id=trade_id,
        buyer="0xbuyer",
        seller="0xseller",
    )


def market(
    offset_ms: int,
    direction: str | None = "long",
    quantity: float = 0.04,
) -> RuntimeMarketState:
    """Return one already-classified backend market decision."""
    return RuntimeMarketState(
        symbol="BTC",
        observed_at=iso(offset_ms),
        entry_direction=direction,
        entry_quantity=quantity,
        entry_limit_price=64_500.0 if direction is not None else None,
        evidence_fresh=True,
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        target_price_fraction=0.002,
        price_tick=1.0,
    )


def controller() -> HypervelocityShadowController:
    """Return one zero-latency deterministic shadow controller."""
    port = NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=10_000.0,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=0,
            cancel_latency_ms=50,
            update_latency_ms=0,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=40.0,
        maintenance_rate=0.0125,
        max_event_age_ms=3_000,
    )
    return HypervelocityShadowController(port=port, initial_market=market(0, None))


def test_partial_entry_fill_immediately_submits_proportional_target() -> None:
    runtime = controller()
    runtime.ingest(l2(0))

    submitted = runtime.on_market(market(1))
    assert [event.event_type for event in submitted.venue_events] == ["submitted"]
    entry = submitted.commands[0]

    accepted = runtime.ingest(l2(2))
    assert [event.event_type for event in accepted.venue_events] == ["accepted"]

    partial = runtime.ingest(trade(3, size=0.021, trade_id=1))
    assert [event.event_type for event in partial.venue_events] == [
        "partially_filled",
        "submitted",
    ]
    assert partial.venue_events[0].client_order_id == entry.client_order_id
    target = partial.commands[0]
    assert target.order_role == "target"
    assert target.quantity == pytest.approx(0.02)
    assert runtime.state.position_quantity == pytest.approx(0.02)


def test_declared_gap_preserves_pending_order_without_fill() -> None:
    runtime = controller()
    runtime.ingest(l2(0))
    runtime.on_market(market(1))
    runtime.ingest(l2(2))

    from hypervector.data.hl_events import StreamGap

    gap = StreamGap(
        symbol="BTC",
        channel="trades",
        detected_ts_ns=(BASE_MS + 3) * 1_000_000,
        reason="websocket_reconnect",
        previous_exchange_ts_ms=BASE_MS + 2,
        next_exchange_ts_ms=BASE_MS + 10,
    )
    uncertain = runtime.ingest(gap)
    missed = runtime.ingest(trade(5, size=1.0, trade_id=2))

    assert uncertain.annotations == ("execution_evidence_uncertain",)
    assert missed.venue_events == ()
    assert runtime.state.pending_entry is not None
    assert runtime.state.position_quantity == 0.0


def test_direction_change_routes_cancel_through_same_execution_port() -> None:
    runtime = controller()
    runtime.ingest(l2(0))
    submitted = runtime.on_market(market(1))
    entry_id = submitted.commands[0].client_order_id
    runtime.ingest(l2(2))

    changed = runtime.on_market(market(3, "short"))

    assert changed.cancellations == (entry_id,)
    assert [event.event_type for event in changed.venue_events] == ["cancel_pending"]


def test_stale_last_book_cannot_authorize_a_new_order() -> None:
    runtime = controller()
    runtime.ingest(l2(0))

    stale = runtime.on_market(market(5_000))

    assert stale.commands == ()
    assert stale.annotations == ("execution_evidence_uncertain",)


def test_rejected_target_is_replaced_without_changing_strategy_eligibility() -> None:
    runtime = controller()
    runtime.ingest(l2(0))
    runtime.on_market(market(1))
    runtime.ingest(l2(2))
    partial = runtime.ingest(trade(3, size=0.021, trade_id=1))
    first_target = partial.commands[0]

    rejected = runtime.ingest(l2(4, bid=64_630.0, ask=64_631.0))

    assert [event.event_type for event in rejected.venue_events] == [
        "rejected",
        "submitted",
    ]
    assert rejected.commands[0].client_order_id != first_target.client_order_id
    assert rejected.commands[0].quantity == pytest.approx(0.02)
    assert runtime.state.position_quantity == pytest.approx(0.02)


def test_partial_liquidation_replaces_target_for_remaining_position() -> None:
    runtime = controller()
    quantity = 280_000.0 / 64_500.0
    runtime.ingest(l2(0))
    runtime.on_market(market(1, quantity=quantity))
    runtime.ingest(l2(2))
    filled = runtime.ingest(trade(3, size=quantity + 0.001, trade_id=9))
    first_target = filled.commands[0]
    boundary = runtime.port.liquidation_price
    assert boundary is not None
    execution_mark = boundary - 0.01
    partial_quantity = quantity * 0.20
    runtime.ingest(
        l2(
            100,
            bid_size=partial_quantity,
            bid=execution_mark,
            ask=execution_mark + 1.0,
        )
    )

    assert runtime.port.mark(mark_price=execution_mark, observed_at=iso(101)) is True
    cycle = runtime.reconcile_liquidation(iso(101))

    assert any(
        event.client_order_id == first_target.client_order_id
        and event.event_type == "canceled"
        for event in cycle.venue_events
    )
    replacement = cycle.commands[0]
    assert replacement.order_role == "target"
    assert replacement.client_order_id != first_target.client_order_id
    assert replacement.quantity == pytest.approx(quantity * 0.80)
    assert runtime.state.position_quantity == pytest.approx(quantity * 0.80)
