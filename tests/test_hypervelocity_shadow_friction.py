"""Deterministic event-friction tests for Hypervelocity shadow execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from hypervector.data.hl_events import (
    AggressorSide,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.execution import OrderCommand
from hypervector.nautilus.hypervelocity_sim import HypervelocitySimulationConfig
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort

BASE_MS = 1_785_103_200_000


def iso(offset_ms: int) -> str:
    """Return a UTC timestamp offset from the deterministic tape origin."""
    return datetime.fromtimestamp((BASE_MS + offset_ms) / 1_000, tz=UTC).isoformat()


def book(
    offset_ms: int,
    *,
    bid_size: float = 0.03,
    bid: float = 64_500.0,
    ask: float = 64_501.0,
) -> L2SnapshotEvent:
    """Return one complete BTC L2 snapshot."""
    exchange_ms = BASE_MS + offset_ms
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        bids=(BookLevel(bid, bid_size, 1),),
        asks=(BookLevel(ask, 0.5, 1),),
    )


def trade(
    offset_ms: int,
    *,
    side: AggressorSide = "sell",
    price: float = 64_500.0,
    size: float = 0.01,
    trade_id: int = 1,
) -> PublicTradeEvent:
    """Return one public aggressor trade."""
    exchange_ms = BASE_MS + offset_ms
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side=side,
        price=price,
        size=size,
        transaction_hash=f"0x{trade_id}",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        trade_id=trade_id,
        buyer="0xbuyer",
        seller="0xseller",
    )


def entry(
    *,
    quantity: float = 0.04,
    limit: float = 64_500.0,
    submitted_ms: int = 0,
) -> OrderCommand:
    """Return one post-only long entry command."""
    return OrderCommand(
        client_order_id="hv-entry-1",
        symbol="BTC",
        side="buy",
        quantity=quantity,
        order_type="limit",
        order_role="entry",
        limit_price=limit,
        post_only=True,
        reduce_only=False,
        submitted_at=iso(submitted_ms),
    )


def maximum_hold_exit(*, quantity: float = 0.01) -> OrderCommand:
    """Return one immediate reduce-only maximum-hold exit command."""
    return OrderCommand(
        client_order_id="hv-exit-1",
        symbol="BTC",
        side="sell",
        quantity=quantity,
        order_type="market",
        order_role="exit",
        limit_price=None,
        post_only=False,
        reduce_only=True,
        submitted_at=iso(3),
    )


def port(
    *,
    submit_ms: int = 50,
    cancel_ms: int = 50,
    initial_cash_usd: float = 120.0,
) -> NautilusShadowExecutionPort:
    """Return a deterministic isolated-margin shadow port."""
    return NautilusShadowExecutionPort(
        symbol="BTC",
        initial_cash_usd=initial_cash_usd,
        simulation_config=HypervelocitySimulationConfig(
            submit_latency_ms=submit_ms,
            cancel_latency_ms=cancel_ms,
            update_latency_ms=50,
        ),
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        leverage=40.0,
        maintenance_rate=0.0125,
        max_event_age_ms=3_000,
    )


def test_latency_queue_ahead_partial_fill_and_account_fee() -> None:
    shadow = port()
    shadow.ingest(book(0))
    assert shadow.submit(entry()).event_type == "submitted"

    shadow.ingest(trade(25, size=1.0))
    assert shadow.reconcile() == ()

    shadow.ingest(book(50))
    accepted = shadow.reconcile()
    assert [item.event_type for item in accepted] == ["accepted"]
    assert shadow.order_telemetry("hv-entry-1").queue_ahead_quantity == 0.03

    shadow.ingest(trade(60, size=0.02, trade_id=2))
    assert shadow.reconcile() == ()
    assert shadow.order_telemetry("hv-entry-1").queue_ahead_quantity == pytest.approx(
        0.01
    )

    shadow.ingest(trade(70, size=0.03, trade_id=3))
    partial = shadow.reconcile()
    assert len(partial) == 1
    assert partial[0].event_type == "partially_filled"
    assert partial[0].last_quantity == pytest.approx(0.02)
    assert partial[0].fee_usd == pytest.approx(0.1935)
    assert shadow.account_snapshot().position_quantity == pytest.approx(0.02)

    record = shadow.execution_records()[-1]
    assert record.execution_model == "nautilus_event_v1"
    assert record.requested_quantity == pytest.approx(0.04)
    assert record.cumulative_filled_quantity == pytest.approx(0.02)
    assert record.remaining_quantity == pytest.approx(0.02)
    assert record.liquidity_side == "maker"


def test_maximum_hold_market_exit_uses_fresh_bbo_taker_and_cancels_target() -> None:
    """A deadline exit consumes BBO and atomically retires passive targets."""
    shadow = port(submit_ms=0, initial_cash_usd=10_000.0)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(trade(2, size=0.011, trade_id=30))
    shadow.reconcile()
    target = replace(
        entry(quantity=0.01),
        client_order_id="hv-target-1",
        side="sell",
        order_role="target",
        limit_price=64_629.0,
        reduce_only=True,
    )
    shadow.submit(target)
    shadow.ingest(book(3, bid_size=0.001))
    shadow.reconcile()

    events, record = shadow.execute_market(
        maximum_hold_exit(),
        observed_at=iso(3),
    )

    assert [event.event_type for event in events] == ["canceled", "filled"]
    assert events[0].client_order_id == "hv-target-1"
    assert events[1].client_order_id == "hv-exit-1"
    assert events[1].fill_price == pytest.approx(64_500.0)
    assert events[1].liquidity_side == "taker"
    assert events[1].fee_usd == pytest.approx(0.01 * 64_500.0 * 0.00045)
    assert record.liquidity_side == "taker"
    assert record.queue_ahead_quantity == 0.0
    assert shadow.account_snapshot().position_quantity == 0.0


def test_partial_target_releases_closed_cost_basis_before_liquidation() -> None:
    """A profitable partial target must not leave all costs on the residue."""
    shadow = port(submit_ms=0, initial_cash_usd=10_000.0)
    quantity = 4.0
    remaining = 0.05
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=quantity))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(trade(2, size=quantity + 0.001, trade_id=20))
    shadow.reconcile()
    shadow.apply_funding(
        hourly_rate=0.0001,
        mark_price=64_500.0,
        applied_at=iso(3),
    )
    target = replace(
        entry(quantity=quantity - remaining),
        client_order_id="hv-target-residual",
        side="sell",
        order_role="target",
        limit_price=64_629.0,
        reduce_only=True,
    )
    shadow.submit(target)
    shadow.ingest(book(4, bid=64_628.0, ask=64_629.0))
    shadow.reconcile()
    shadow.ingest(
        trade(
            5,
            side="buy",
            price=64_629.0,
            size=quantity - remaining + 0.5,
            trade_id=21,
        )
    )
    shadow.reconcile()

    assert shadow.account_snapshot().position_quantity == pytest.approx(remaining)
    assert shadow.funding_net_usd == pytest.approx(-0.3225)
    boundary = shadow.liquidation_price
    assert boundary is not None
    assert boundary < 64_500.0
    shadow.ingest(book(6, bid=64_628.0, ask=64_629.0))
    assert shadow.mark(mark_price=64_629.0, observed_at=iso(7)) is False
    assert shadow.last_liquidation is None


def test_post_only_cross_rejects_after_submit_latency() -> None:
    shadow = port()
    shadow.ingest(book(0))
    shadow.submit(entry(limit=64_501.0))

    shadow.ingest(book(50))
    events = shadow.reconcile()

    assert len(events) == 1
    assert events[0].event_type == "rejected"
    assert events[0].reason == "post_only_would_cross"
    assert shadow.account_snapshot().position_quantity == 0.0


def test_trade_through_fills_resting_order_at_its_limit_not_later_print() -> None:
    shadow = port(submit_ms=0)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()

    shadow.ingest(trade(2, price=64_499.0, size=0.011, trade_id=12))
    events = shadow.reconcile()

    assert events[0].fill_price == pytest.approx(64_500.0)


def test_cancel_latency_allows_fill_before_cancel_becomes_effective() -> None:
    shadow = port(submit_ms=0, cancel_ms=50)
    shadow.ingest(book(0, bid_size=0.0 + 0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()

    pending = shadow.cancel("hv-entry-1", requested_at=iso(10))
    assert pending.event_type == "cancel_pending"
    shadow.ingest(trade(20, size=0.02, trade_id=4))
    events = shadow.reconcile()

    assert [item.event_type for item in events] == ["filled"]
    assert shadow.account_snapshot().position_quantity == pytest.approx(0.01)


def test_effective_cancel_prevents_later_trade_fill() -> None:
    shadow = port(submit_ms=0, cancel_ms=50)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.cancel("hv-entry-1", requested_at=iso(10))

    shadow.ingest(book(60, bid_size=0.001))
    shadow.ingest(trade(70, size=1.0, trade_id=5))
    events = shadow.reconcile()

    assert [item.event_type for item in events] == ["canceled"]
    assert shadow.account_snapshot().position_quantity == 0.0


def test_cancel_requested_before_ack_still_allows_pre_cancel_fill() -> None:
    shadow = port(submit_ms=50, cancel_ms=100)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.cancel("hv-entry-1", requested_at=iso(10))

    shadow.ingest(book(60, bid_size=0.001))
    shadow.ingest(trade(70, size=0.011, trade_id=9))
    events = shadow.reconcile()

    assert [item.event_type for item in events] == ["accepted", "filled"]
    assert shadow.account_snapshot().position_quantity == pytest.approx(0.01)


def test_gap_and_stale_book_preserve_order_without_claiming_fill() -> None:
    shadow = port(submit_ms=0)
    assert shadow.liquidation_cooldown_until_ms is None
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(
        StreamGap(
            symbol="BTC",
            channel="trades",
            detected_ts_ns=(BASE_MS + 2) * 1_000_000,
            reason="websocket_reconnect",
            previous_exchange_ts_ms=BASE_MS + 1,
            next_exchange_ts_ms=BASE_MS + 100,
        )
    )
    shadow.ingest(trade(50, size=1.0, trade_id=6))

    assert shadow.reconcile() == ()
    telemetry = shadow.order_telemetry("hv-entry-1")
    assert telemetry.remaining_quantity == pytest.approx(0.01)
    assert telemetry.evidence_fresh is False
    assert shadow.execution_annotations()[-1] == "execution_evidence_uncertain"

    shadow.ingest(book(100, bid_size=0.001))
    shadow.ingest(trade(110, size=0.011, trade_id=7))
    assert [item.event_type for item in shadow.reconcile()] == ["filled"]


def test_late_or_duplicate_trade_evidence_cannot_double_fill() -> None:
    shadow = port(submit_ms=0)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.02))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    late = replace(
        trade(2, size=1.0, trade_id=10),
        received_ts_ns=(BASE_MS + 4_002) * 1_000_000,
    )
    shadow.ingest(late)
    assert shadow.reconcile() == ()

    shadow.ingest(book(3, bid_size=0.001))
    partial = trade(4, size=0.011, trade_id=11)
    shadow.ingest(partial)
    shadow.ingest(partial)
    events = shadow.reconcile()

    assert len(events) == 1
    assert events[0].last_quantity == pytest.approx(0.01)
    assert shadow.account_snapshot().position_quantity == pytest.approx(0.01)


def test_stale_book_cannot_acknowledge_or_fill_a_delayed_submission() -> None:
    shadow = port(submit_ms=5_000)
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=0.01))

    shadow.ingest(trade(5_001, size=1.0, trade_id=13))

    assert shadow.reconcile() == ()
    telemetry = shadow.order_telemetry("hv-entry-1")
    assert telemetry.status == "pending"
    assert telemetry.evidence_fresh is False
    assert telemetry.cumulative_filled_quantity == 0.0


def test_hourly_funding_and_isolated_liquidation_are_accounted() -> None:
    shadow = port(submit_ms=0)
    quantity = 3_360.0 / 64_500.0
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=quantity))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(trade(2, size=quantity + 0.001, trade_id=8))
    shadow.reconcile()
    target = replace(
        entry(quantity=quantity),
        client_order_id="hv-target-1",
        side="sell",
        order_role="target",
        limit_price=64_629.0,
        reduce_only=True,
    )
    shadow.submit(target)
    shadow.ingest(book(3, bid_size=0.001))
    shadow.reconcile()

    assert shadow.position_margin_usd == pytest.approx(84.0)
    funding = shadow.apply_funding(
        hourly_rate=0.0001,
        mark_price=64_500.0,
        applied_at=iso(3_600_000),
    )
    assert funding == pytest.approx(-0.336)
    assert shadow.funding_net_usd == pytest.approx(-0.336)

    liquidation_price = shadow.liquidation_price
    assert liquidation_price is not None
    assert (
        shadow.mark(
            mark_price=liquidation_price + 0.01,
            observed_at=iso(3_600_001),
        )
        is False
    )
    execution_mark = liquidation_price - 0.01
    shadow.ingest(
        book(
            3_600_001,
            bid_size=quantity,
            bid=execution_mark,
            ask=execution_mark + 1.0,
        )
    )
    assert (
        shadow.mark(
            mark_price=execution_mark,
            observed_at=iso(3_600_002),
        )
        is True
    )
    assert shadow.account_snapshot().position_quantity == 0.0
    assert shadow.last_liquidation is not None
    assert shadow.last_liquidation.margin_mode == "isolated"
    assert shadow.last_liquidation.boundary_price == pytest.approx(liquidation_price)
    assert shadow.last_liquidation.mark_price == pytest.approx(execution_mark)
    assert shadow.last_liquidation.execution_fee_usd == pytest.approx(
        quantity * execution_mark * 0.00045
    )
    assert shadow.last_liquidation.clearance_fee_usd == 0.0
    assert (
        shadow.last_liquidation.execution_model == "hyperliquid_market_liquidation_v2"
    )
    canceled = shadow.reconcile()
    assert [item.event_type for item in canceled] == ["canceled"]
    assert canceled[0].reason == "isolated_liquidation"


def test_large_liquidation_uses_twenty_percent_then_full_cooldown_attempt() -> None:
    shadow = port(submit_ms=0, initial_cash_usd=10_000.0)
    quantity = 280_000.0 / 64_500.0
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=quantity))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(trade(2, size=quantity + 0.001, trade_id=81))
    shadow.reconcile()

    first_boundary = shadow.liquidation_price
    assert first_boundary is not None
    first_mark = first_boundary - 0.01
    first_quantity = quantity * 0.20
    shadow.ingest(
        book(
            100,
            bid_size=first_quantity,
            bid=first_mark,
            ask=first_mark + 1.0,
        )
    )

    assert shadow.mark(mark_price=first_mark, observed_at=iso(101)) is True
    first = shadow.last_liquidation
    assert first is not None
    assert first.method == "market"
    assert first.partial_rule_applied is True
    assert first.attempted_quantity == pytest.approx(first_quantity)
    assert first.filled_quantity == pytest.approx(first_quantity)
    assert first.remaining_quantity == pytest.approx(quantity * 0.80)
    assert first.execution_price == pytest.approx(first_mark)
    assert first.cooldown_until_ms == BASE_MS + 30_101
    assert shadow.account_snapshot().position_quantity == pytest.approx(quantity * 0.80)

    second_boundary = shadow.liquidation_price
    assert second_boundary is not None
    second_mark = second_boundary - 0.01
    remaining = quantity * 0.80
    shadow.ingest(
        book(
            1_000,
            bid_size=remaining,
            bid=second_mark,
            ask=second_mark + 1.0,
        )
    )

    assert shadow.mark(mark_price=second_mark, observed_at=iso(1_001)) is True
    second = shadow.last_liquidation
    assert second is not None
    assert second.partial_rule_applied is False
    assert second.attempted_quantity == pytest.approx(remaining)
    assert second.filled_quantity == pytest.approx(remaining)
    assert second.remaining_quantity == 0.0
    assert shadow.account_snapshot().position_quantity == 0.0


def test_deep_underwater_position_backstops_after_insufficient_market_depth() -> None:
    shadow = port(submit_ms=0, initial_cash_usd=10_000.0)
    quantity = 280_000.0 / 64_500.0
    shadow.ingest(book(0, bid_size=0.001))
    shadow.submit(entry(quantity=quantity))
    shadow.ingest(book(1, bid_size=0.001))
    shadow.reconcile()
    shadow.ingest(trade(2, size=quantity + 0.001, trade_id=82))
    shadow.reconcile()

    boundary = shadow.liquidation_price
    assert boundary is not None
    deep_mark = boundary - 500.0
    shadow.ingest(
        book(
            100,
            bid_size=0.01,
            bid=deep_mark,
            ask=deep_mark + 1.0,
        )
    )

    assert shadow.mark(mark_price=deep_mark, observed_at=iso(101)) is True
    liquidation = shadow.last_liquidation
    assert liquidation is not None
    assert liquidation.method == "backstop"
    assert liquidation.market_filled_quantity == pytest.approx(0.01)
    assert liquidation.backstop_quantity == pytest.approx(quantity - 0.01)
    assert liquidation.filled_quantity == pytest.approx(quantity)
    assert liquidation.remaining_quantity == 0.0
    assert shadow.account_snapshot().position_quantity == 0.0
