"""Offline contracts for the streamed Apex MM venue facade."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.live.apex_mm_streaming_venue import (
    ApexMMStreamingVenue,
    ApexMMStreamingVenueError,
)
from hypervector.live.apex_mm_venue_stream import (
    ApexMMVenueStreamError,
    ApexMMVenueStreamSnapshot,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidPostOnlyOrder,
    HyperliquidOrderStatus,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFill,
    SolMarketMetadata,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_order_transport import (
    HyperliquidBatchOrderTransportError,
    SolCancelTransportError,
)


def _position(size: float = 0.0) -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size,
        100.0 if size else None,
        70.0 if size > 0 else 130.0 if size < 0 else None,
        abs(size) * 100.0 / 3.0,
        abs(size) * 100.0,
        0.0,
        "isolated" if size else None,
        3 if size else None,
    )


def _venue(
    *orders: SolOpenOrder,
    size: float = 0.0,
    fills: tuple[SolFill, ...] = (),
) -> SolReconciliationSnapshot:
    position = _position(size)
    account = SolAccountSnapshot(
        153.61,
        153.61,
        position.margin_used_usd,
        position.position_value_usd,
        position,
    )
    return SolReconciliationSnapshot(account, tuple(orders), fills)


def _book() -> SolBookSnapshot:
    return SolBookSnapshot(
        1_725_000_000_000,
        (SolBookLevel(100.0, 2.0, 1),),
        (SolBookLevel(101.0, 2.0, 1),),
        100.5,
        99.5,
        2.0,
        2.0,
        0.0,
    )


def _order(oid: int, side: str) -> SolOpenOrder:
    return SolOpenOrder(
        oid,
        0.1,
        0.1,
        side,
        False,
        False,
        None,
        "Limit",
        1_725_000_000_000,
        100.0 if side == "B" else 101.0,
    )


def _fill(oid: int) -> SolFill:
    return SolFill(
        oid,
        100.0,
        0.1,
        "A",
        1_725_000_000_100,
        0.0045,
        "USDC",
        0.0,
        True,
        "Close Long",
        "0xcleanup",
        oid + 30_000,
    )


class _Stream:
    def __init__(self, venue: SolReconciliationSnapshot) -> None:
        self.current = ApexMMVenueStreamSnapshot(_book(), venue)
        self.started = 0
        self.closed = 0
        self.waited_for: list[frozenset[int]] = []
        self.waited_fill_oids: list[int] = []

    def start(self, *, timeout_seconds: float) -> None:
        assert timeout_seconds > 0.0
        self.started += 1

    def snapshot(self, *, maximum_age_ms: int) -> ApexMMVenueStreamSnapshot:
        assert maximum_age_ms >= 0
        return self.current

    def state_snapshot(self) -> ApexMMVenueStreamSnapshot:
        return self.current

    def wait_for_fresh_book(
        self,
        *,
        maximum_age_ms: int,
        timeout_seconds: float,
    ) -> SolBookSnapshot:
        assert maximum_age_ms >= 0 and timeout_seconds > 0.0
        return self.current.book

    def wait_for_open_orders(
        self,
        *,
        expected_oids: frozenset[int],
        timeout_seconds: float,
        maximum_age_ms: int,
    ) -> ApexMMVenueStreamSnapshot:
        assert timeout_seconds > 0.0 and maximum_age_ms >= 0
        self.waited_for.append(expected_oids)
        orders = tuple(
            _order(oid, "B" if index == 0 else "A")
            for index, oid in enumerate(sorted(expected_oids))
        )
        self.current = ApexMMVenueStreamSnapshot(_book(), _venue(*orders))
        return self.current

    def wait_for_fill(
        self,
        *,
        oid: int,
        timeout_seconds: float,
        markout_horizon_ms: int = 0,
    ) -> ApexMMVenueStreamSnapshot:
        assert timeout_seconds > 0.0 and markout_horizon_ms >= 0
        self.waited_fill_oids.append(oid)
        self.current = ApexMMVenueStreamSnapshot(
            _book(),
            _venue(fills=(_fill(oid),)),
        )
        return self.current

    def close(self) -> None:
        self.closed += 1


class _TimedOutOrderStream(_Stream):
    def wait_for_open_orders(
        self,
        *,
        expected_oids: frozenset[int],
        timeout_seconds: float,
        maximum_age_ms: int,
    ) -> ApexMMVenueStreamSnapshot:
        del expected_oids, timeout_seconds, maximum_age_ms
        raise ApexMMVenueStreamError("venue stream order confirmation timed out")


class _TimedOutFillStream(_Stream):
    def wait_for_fill(
        self,
        *,
        oid: int,
        timeout_seconds: float,
        markout_horizon_ms: int = 0,
    ) -> ApexMMVenueStreamSnapshot:
        del oid, timeout_seconds, markout_horizon_ms
        raise ApexMMVenueStreamError("venue stream fill confirmation timed out")


class _Delegate:
    def __init__(self, venue: SolReconciliationSnapshot) -> None:
        self.venue = venue
        self.calls: list[str] = []
        self.next_oid = 10

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        assert expected_max_leverage == 40
        self.calls.append("preflight")
        return SolVenuePreflight(
            SolMarketMetadata("BTC", 5, 40),
            100.5,
            1.0,
            0.00001,
            HyperliquidFeeSchedule(0.00015, 0.00045),
            153.61,
            153.61,
            self.venue.position,
            "unifiedAccount",
        )

    def reconcile(self) -> SolReconciliationSnapshot:
        self.calls.append("rest_reconcile")
        return self.venue

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        self.calls.append("rest_book")
        return _book()

    def configure_isolated_leverage(self, leverage: int) -> None:
        self.calls.append(f"leverage:{leverage}")

    def submit_entry(self, **_kwargs: object) -> HyperliquidOrderAck:
        oid = self.next_oid
        self.next_oid += 1
        return HyperliquidOrderAck(True, oid, "resting")

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]:
        return tuple(self.submit_entry(side=order.side) for order in orders)

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        return HyperliquidOrderAck(True, oid, "canceled")

    def close_position(self, **_kwargs: object) -> HyperliquidOrderAck:
        return HyperliquidOrderAck(True, 99, "filled")

    def order_status(self, oid: int) -> object:
        raise AssertionError(f"unexpected order_status({oid})")

    def order_status_by_client_id(self, client_order_id: str) -> object:
        raise AssertionError(f"unexpected order_status({client_order_id})")

    def funding_payments(self, **_kwargs: int) -> tuple[()]:
        return ()


class _FilledDuringCancelDelegate(_Delegate):
    def __init__(self, venue: SolReconciliationSnapshot) -> None:
        super().__init__(venue)
        self.filled_oid: int | None = None

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        if self.filled_oid == oid:
            raise SolCancelTransportError(
                operation="cancel_order",
                oid=oid,
                detail="order filled before cancel reached matching engine",
            )
        return super().cancel_order(oid)

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        assert oid == self.filled_oid
        return HyperliquidOrderStatus(oid, "BTC", "filled", 0.1, 1_725_000_000_100)


class _LostBatchResponseDelegate(_Delegate):
    def __init__(self, venue: SolReconciliationSnapshot) -> None:
        super().__init__(venue)
        self.recovered: dict[str, HyperliquidOrderStatus] = {}

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]:
        for order in orders:
            oid = self.next_oid
            self.next_oid += 1
            self.recovered[order.client_order_id] = HyperliquidOrderStatus(
                oid,
                "BTC",
                "open",
                0.1,
                1_725_000_000_100,
                order.client_order_id,
            )
        raise HyperliquidBatchOrderTransportError(
            operation="post-only quote batch",
            client_order_ids=tuple(order.client_order_id for order in orders),
            detail="injected response loss",
        )

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        return self.recovered[client_order_id]


def _facade(
    delegate: _Delegate,
    stream: _Stream,
    *,
    monotonic_fn: object = lambda: 0.0,
    sleep_fn: object = lambda _seconds: None,
) -> ApexMMStreamingVenue:
    return ApexMMStreamingVenue(
        delegate=delegate,
        stream_factory=lambda _mode: stream,
        maximum_book_age_ms=1_500,
        confirmation_timeout_seconds=2.0,
        authoritative_reconcile_seconds=60.0,
        monotonic_fn=monotonic_fn,
        sleep_fn=sleep_fn,
    )


def test_preflight_starts_stream_and_reconcile_uses_stream_state() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)

    facade.preflight(expected_max_leverage=40)
    observed = facade.reconcile()
    facade.close()

    assert observed.account.account_value_usd == pytest.approx(153.61)
    assert stream.started == 1 and stream.closed == 1
    assert delegate.calls == ["preflight"]


def test_live_book_uses_fresh_low_weight_rest_l2() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)

    observed = facade.book_snapshot(depth_levels=5)

    assert observed.mid_price == pytest.approx(100.5)
    assert delegate.calls == ["preflight", "rest_book"]


def test_mutations_are_confirmed_by_exact_streamed_order_identity() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)

    first = facade.submit_entry(side="buy")
    second = facade.submit_entry(side="sell")
    facade.reconcile()
    facade.cancel_order(first.oid or 0)
    facade.cancel_order(second.oid or 0)
    facade.reconcile()

    assert stream.waited_for == [frozenset({10, 11}), frozenset()]


def test_batch_quote_mutation_registers_both_oids_before_confirmation() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    requests = (
        HyperliquidPostOnlyOrder("buy", 12.5, 100.0, "0x" + "1" * 32),
        HyperliquidPostOnlyOrder("sell", 12.5, 101.0, "0x" + "2" * 32),
    )

    acknowledgements = facade.submit_post_only_batch(requests)
    facade.reconcile()

    assert [ack.oid for ack in acknowledgements] == [10, 11]
    assert stream.waited_for == [frozenset({10, 11})]


def test_recovered_batch_identities_join_stream_confirmation_set() -> None:
    delegate = _LostBatchResponseDelegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    requests = (
        HyperliquidPostOnlyOrder("buy", 12.5, 100.0, "0x" + "1" * 32),
        HyperliquidPostOnlyOrder("sell", 12.5, 101.0, "0x" + "2" * 32),
    )

    with pytest.raises(HyperliquidBatchOrderTransportError):
        facade.submit_post_only_batch(requests)
    statuses = tuple(
        facade.order_status_by_client_id(request.client_order_id)
        for request in requests
    )
    facade.reconcile()

    assert [status.oid for status in statuses] == [10, 11]
    assert stream.waited_for == [frozenset({10, 11})]


def test_exact_filled_status_retires_stream_expectation_after_cancel_race() -> None:
    delegate = _FilledDuringCancelDelegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    bid = facade.submit_entry(side="buy")
    ask = facade.submit_entry(side="sell")
    facade.reconcile()
    assert bid.oid is not None and ask.oid is not None
    delegate.filled_oid = ask.oid

    with pytest.raises(SolCancelTransportError):
        facade.cancel_order(ask.oid)
    status = facade.order_status(ask.oid)
    facade.cancel_order(bid.oid)
    facade.reconcile()

    assert status.status == "filled"
    assert stream.waited_for == [frozenset({bid.oid, ask.oid}), frozenset()]


def test_fill_snapshot_retires_expected_oid_before_remaining_quote_cancel() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    bid = facade.submit_entry(side="buy")
    ask = facade.submit_entry(side="sell")
    facade.reconcile()
    assert bid.oid is not None and ask.oid is not None
    stream.current = ApexMMVenueStreamSnapshot(
        _book(),
        _venue(_order(ask.oid, "A"), size=0.1),
    )

    observed = facade.reconcile()
    facade.cancel_order(ask.oid)
    facade.reconcile()

    assert [order.oid for order in observed.open_orders] == [ask.oid]
    assert stream.waited_for == [frozenset({bid.oid, ask.oid}), frozenset()]


def test_timed_out_order_stream_uses_exact_authoritative_rest_confirmation() -> None:
    resting = _order(41, "B")
    delegate = _Delegate(_venue(resting))
    stream = _TimedOutOrderStream(_venue(resting))
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    facade.cancel_order(resting.oid)
    delegate.venue = _venue()

    observed = facade.reconcile()

    assert observed.is_flat
    assert delegate.calls[-1] == "rest_reconcile"


def test_timed_out_order_stream_rejects_rest_order_identity_mismatch() -> None:
    resting = _order(41, "B")
    delegate = _Delegate(_venue(resting))
    stream = _TimedOutOrderStream(_venue(resting))
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    facade.cancel_order(resting.oid)

    with pytest.raises(ApexMMStreamingVenueError, match="REST confirmation mismatch"):
        facade.reconcile()


def test_shutdown_switches_reconciliation_and_book_to_rest() -> None:
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)

    facade.begin_shutdown()
    facade.reconcile()
    facade.book_snapshot(depth_levels=1)

    assert delegate.calls[-2:] == ["rest_reconcile", "rest_book"]


def test_shutdown_fill_wait_uses_private_fill_stream() -> None:
    delegate = _Delegate(_venue(size=0.1))
    stream = _Stream(_venue(size=0.1))
    facade = _facade(delegate, stream)
    facade.preflight(expected_max_leverage=40)
    facade.begin_shutdown()

    observed, markout = facade.wait_for_fill(99, 0)

    assert stream.waited_fill_oids == [99]
    assert [fill.oid for fill in observed.fills] == [99]
    assert markout.mid_price == pytest.approx(100.5)


def test_timed_out_fill_stream_waits_for_eventually_consistent_rest_fill() -> None:
    class _LaggedFillDelegate(_Delegate):
        def __init__(self) -> None:
            super().__init__(_venue())
            self.reconciliations = 0

        def reconcile(self) -> SolReconciliationSnapshot:
            self.reconciliations += 1
            if self.reconciliations >= 2:
                self.venue = _venue(fills=(_fill(99),))
            return super().reconcile()

        def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
            assert depth_levels == 1
            return replace(_book(), exchange_timestamp_ms=1_725_000_001_100)

    now = [0.0]
    delegate = _LaggedFillDelegate()
    stream = _TimedOutFillStream(_venue())
    facade = _facade(
        delegate,
        stream,
        monotonic_fn=lambda: now[0],
        sleep_fn=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    facade.preflight(expected_max_leverage=40)

    venue, markout = facade.wait_for_fill(99, 1_000)

    assert delegate.reconciliations == 2
    assert [fill.oid for fill in venue.fills] == [99]
    assert markout.exchange_timestamp_ms == 1_725_000_001_100


def test_periodic_authoritative_mismatch_fails_closed() -> None:
    now = [0.0]
    delegate = _Delegate(_venue())
    stream = _Stream(_venue())
    facade = _facade(delegate, stream, monotonic_fn=lambda: now[0])
    facade.preflight(expected_max_leverage=40)
    now[0] = 61.0
    delegate.venue = replace(delegate.venue, open_orders=(_order(90, "B"),))

    with pytest.raises(ApexMMStreamingVenueError, match="drift"):
        facade.reconcile()
