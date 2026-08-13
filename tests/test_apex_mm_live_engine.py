"""Failure-injected lifecycle tests for the Apex MM live canary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.live.apex_mm_live_config import load_apex_mm_live_config
from hypervector.live.apex_mm_live_engine import (
    ApexMMLiveEngine,
    ApexMMLiveEngineError,
    ApexMMLiveState,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidPostOnlyOrder,
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
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.sol_order_transport import (
    HyperliquidBatchOrderTransportError,
    SolCancelTransportError,
    SolOrderTransportError,
)


_CONFIG = Path("configs/apex_regime_mm_canary.toml")
_QUOTE_REFRESH_MS = load_apex_mm_live_config(_CONFIG).quote_refresh_ms


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, milliseconds: int) -> None:
        self.now += timedelta(milliseconds=milliseconds)


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def emit_preflight(self, preflight: object, venue: object) -> None:
        self.events.append(("preflight", preflight))

    def emit_reconciliation(self, venue: object) -> None:
        self.events.append(("reconciliation", venue))

    def emit_book(self, book: object) -> None:
        self.events.append(("book", book))

    def emit_quote(self, quote: object, inventory_notional_usd: float) -> None:
        self.events.append(("quote", (quote, inventory_notional_usd)))

    def emit_order_intent(self, **payload: object) -> None:
        self.events.append(("order_intent", payload))

    def emit_ack(self, operation: str, ack: object) -> None:
        self.events.append((operation, ack))

    def emit_funding_payments(self, payments: object) -> None:
        self.events.append(("funding", payments))

    def emit_state(self, snapshot: object) -> None:
        self.events.append(("state", snapshot))

    def emit_fault(self, message: str) -> None:
        self.events.append(("fault", message))


def _position(size: float = 0.0) -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=size,
        entry_price=100.5 if size else None,
        liquidation_price=70.0 if size > 0 else 130.0 if size < 0 else None,
        margin_used_usd=abs(size) * 100.5 / 3.0,
        position_value_usd=abs(size) * 100.5,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated" if size else None,
        leverage=3 if size else None,
    )


def _account(position: SolPositionSnapshot | None = None) -> SolAccountSnapshot:
    observed = position or _position()
    return SolAccountSnapshot(
        150.0, 150.0, observed.margin_used_usd, observed.position_value_usd, observed
    )


def _book(
    timestamp_ms: int | None = None,
    *,
    best_bid: float = 100.0,
    best_ask: float = 101.0,
) -> SolBookSnapshot:
    bids = (SolBookLevel(best_bid, 2.0, 1), SolBookLevel(best_bid - 1.0, 3.0, 1))
    asks = (SolBookLevel(best_ask, 2.0, 1), SolBookLevel(best_ask + 1.0, 3.0, 1))
    timestamp = timestamp_ms or int(
        datetime(2026, 8, 1, 12, 0, tzinfo=UTC).timestamp() * 1_000
    )
    mid = (best_bid + best_ask) / 2.0
    spread_bps = (best_ask - best_bid) / mid * 10_000.0
    return SolBookSnapshot(timestamp, bids, asks, mid, spread_bps, 5.0, 5.0, 0.0)


class _Venue:
    def __init__(self) -> None:
        self.account = _account()
        self.orders: list[SolOpenOrder] = []
        self.next_oid = 1
        self.reject_side: str | None = None
        self.transport_side: str | None = None
        self.transport_cancel_oid: int | None = None
        self.status_by_client_id: dict[str, HyperliquidOrderStatus] = {}
        self.status_by_oid: dict[int, HyperliquidOrderStatus] = {}
        self.calls: list[tuple[str, object]] = []
        self.book = _book()

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        assert expected_max_leverage == 40
        return SolVenuePreflight(
            SolMarketMetadata("BTC", 5, 40),
            100.5,
            1.0,
            0.00001,
            HyperliquidFeeSchedule(0.00015, 0.00045),
            150.0,
            150.0,
            self.account.position,
            "unifiedAccount",
        )

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        assert depth_levels >= 1
        return self.book

    def configure_isolated_leverage(self, leverage: int) -> None:
        self.calls.append(("leverage", leverage))

    def reconcile(self) -> SolReconciliationSnapshot:
        return SolReconciliationSnapshot(self.account, tuple(self.orders), ())

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck:
        side = str(kwargs["side"])
        client_order_id = str(kwargs["client_order_id"])
        self.calls.append(("submit", dict(kwargs)))
        if side == self.reject_side:
            return HyperliquidOrderAck(False, None, "rejected", error="injected")
        oid = self.next_oid
        self.next_oid += 1
        self.orders.append(
            SolOpenOrder(
                oid,
                float(kwargs["requested_notional_usd"]) / float(kwargs["limit_price"]),
                float(kwargs["requested_notional_usd"]) / float(kwargs["limit_price"]),
                "B" if side == "buy" else "A",
                False,
                False,
                None,
                "Limit",
                1_000,
                float(kwargs["limit_price"]),
            )
        )
        status = HyperliquidOrderStatus(
            oid,
            "BTC",
            "open",
            self.orders[-1].size,
            1_000,
            client_order_id,
        )
        self.status_by_client_id[client_order_id] = status
        self.status_by_oid[oid] = status
        if side == self.transport_side:
            raise SolOrderTransportError(
                operation="post-only entry",
                client_order_id=client_order_id,
                detail="injected response loss",
            )
        return HyperliquidOrderAck(True, oid, "resting")

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]:
        self.calls.append(("submit_batch", orders))
        acknowledgements = tuple(
            self._accept_post_only_order(order) for order in orders
        )
        if any(order.side == self.transport_side for order in orders):
            raise HyperliquidBatchOrderTransportError(
                operation="post-only quote batch",
                client_order_ids=tuple(order.client_order_id for order in orders),
                detail="injected response loss",
            )
        return acknowledgements

    def _accept_post_only_order(
        self,
        order: HyperliquidPostOnlyOrder,
    ) -> HyperliquidOrderAck:
        if order.side == self.reject_side:
            return HyperliquidOrderAck(False, None, "rejected", error="injected")
        oid = self.next_oid
        self.next_oid += 1
        size = order.requested_notional_usd / order.limit_price
        self.orders.append(
            SolOpenOrder(
                oid,
                size,
                size,
                "B" if order.side == "buy" else "A",
                False,
                False,
                None,
                "Limit",
                1_000,
                order.limit_price,
            )
        )
        status = HyperliquidOrderStatus(
            oid,
            "BTC",
            "open",
            size,
            1_000,
            order.client_order_id,
        )
        self.status_by_client_id[order.client_order_id] = status
        self.status_by_oid[oid] = status
        return HyperliquidOrderAck(
            True,
            oid,
            "resting",
            client_order_id=order.client_order_id,
        )

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        self.calls.append(("cancel", oid))
        self.orders = [order for order in self.orders if order.oid != oid]
        prior = self.status_by_oid.get(oid)
        self.status_by_oid[oid] = HyperliquidOrderStatus(
            oid,
            "BTC",
            "canceled",
            prior.size if prior else 0.0,
            1_001,
            prior.client_order_id if prior else None,
        )
        if oid == self.transport_cancel_oid:
            raise SolCancelTransportError(
                operation="cancel_order",
                oid=oid,
                detail="injected response loss",
            )
        return HyperliquidOrderAck(True, oid, "canceled")

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        return self.status_by_oid[oid]

    def order_status_by_client_id(self, client_order_id: str) -> HyperliquidOrderStatus:
        return self.status_by_client_id[client_order_id]

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck:
        self.calls.append(("close", dict(kwargs)))
        self.account = _account()
        return HyperliquidOrderAck(True, 99, "filled")

    def wait_for_fill(
        self,
        oid: int,
        markout_horizon_ms: int,
    ) -> tuple[SolReconciliationSnapshot, SolBookSnapshot]:
        assert markout_horizon_ms == 1_000
        fill = SolFill(
            oid,
            100.0,
            0.1,
            "B",
            1_725_000_000_100,
            0.0045,
            "USDC",
            0.0,
            True,
            "Close Short",
            "0xcleanup",
            9_001,
        )
        venue = SolReconciliationSnapshot(self.account, tuple(self.orders), (fill,))
        return venue, self.book

    def funding_payments(self, **kwargs: int) -> tuple[()]:
        self.calls.append(("funding", dict(kwargs)))
        return ()

    def begin_shutdown(self) -> None:
        self.calls.append(("begin_shutdown", None))


def _engine(
    venue: _Venue,
    telemetry: _Telemetry,
    clock: _Clock,
) -> ApexMMLiveEngine:
    ids = iter((f"0x{index:032x}" for index in range(1, 100)))
    config = load_apex_mm_live_config(
        _CONFIG,
        enabled=True,
        accepts_live_risk=True,
    )
    return ApexMMLiveEngine(
        config=config,
        adapter=venue,
        telemetry=telemetry,
        credentials_present=True,
        now_fn=clock,
        client_order_id_fn=lambda: next(ids),
    )


def test_unarmed_config_cannot_construct_engine() -> None:
    config = load_apex_mm_live_config(_CONFIG)

    with pytest.raises(Exception, match="--enabled"):
        ApexMMLiveEngine(
            config=config,
            adapter=_Venue(),
            telemetry=_Telemetry(),
            credentials_present=True,
            now_fn=_Clock(),
            client_order_id_fn=lambda: "0x" + "1" * 32,
        )


def test_start_requires_flat_account_then_places_reconciled_quote_pair() -> None:
    venue = _Venue()
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, _Clock())

    snapshot = engine.start()

    assert snapshot.state is ApexMMLiveState.QUOTING
    assert snapshot.bid_oid == 1
    assert snapshot.ask_oid == 2
    assert venue.calls[0] == ("leverage", 3)
    assert [call[0] for call in venue.calls].count("submit_batch") == 1
    submitted = next(value for name, value in venue.calls if name == "submit_batch")
    assert isinstance(submitted, tuple) and len(submitted) == 2
    intents = [
        payload
        for event, payload in telemetry.events
        if event == "order_intent" and payload.get("operation") == "maker_quote"
    ]
    assert len({payload["quote_batch_id"] for payload in intents}) == 1
    assert {payload["book_exchange_timestamp_ms"] for payload in intents} == {
        venue.book.exchange_timestamp_ms
    }
    assert len({payload["batch_submission_started_at_ms"] for payload in intents}) == 1


def test_start_refreshes_book_after_slow_cancellation_reconciliation() -> None:
    clock = _Clock()

    class _SlowReconciliationVenue(_Venue):
        def __init__(self) -> None:
            super().__init__()
            self.reconciliation_count = 0

        def reconcile(self) -> SolReconciliationSnapshot:
            self.reconciliation_count += 1
            if self.reconciliation_count == 2:
                clock.advance(1_500)
            return super().reconcile()

        def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
            assert depth_levels >= 1
            return _book(int(clock.now.timestamp() * 1_000))

    venue = _SlowReconciliationVenue()
    telemetry = _Telemetry()

    snapshot = _engine(venue, telemetry, clock).start()

    assert snapshot.state is ApexMMLiveState.QUOTING
    assert snapshot.bid_oid == 1
    assert snapshot.ask_oid == 2
    assert len([event for event in telemetry.events if event[0] == "book"]) == 1


def test_startup_stream_schema_failure_is_journaled_before_cleanup() -> None:
    class _SchemaFailureVenue(_Venue):
        def __init__(self) -> None:
            super().__init__()
            self.reconciliations = 0

        def reconcile(self) -> SolReconciliationSnapshot:
            self.reconciliations += 1
            if self.reconciliations == 3:
                raise HyperliquidAdapterError("injected order update schema")
            return super().reconcile()

    venue = _SchemaFailureVenue()
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, _Clock())

    snapshot = engine.start()
    stopped = engine.shutdown()

    assert snapshot.state is ApexMMLiveState.FAULT
    assert stopped.state is ApexMMLiveState.STOPPED
    assert venue.orders == []
    assert (
        "fault",
        "venue state failure: injected order update schema",
    ) in telemetry.events


def test_second_quote_rejection_rolls_back_first_order_and_faults() -> None:
    venue = _Venue()
    venue.reject_side = "sell"
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, _Clock())

    snapshot = engine.start()

    assert snapshot.state is ApexMMLiveState.FAULT
    assert venue.orders == []
    assert ("cancel", 1) in venue.calls
    intents = [
        payload for event, payload in telemetry.events if event == "order_intent"
    ]
    assert any(
        payload.get("operation") == "rollback_quote" and payload.get("oid") == 1
        for payload in intents
    )


def test_slow_batch_ack_does_not_delay_second_leg_submission() -> None:
    clock = _Clock()

    class _SlowBatchAckVenue(_Venue):
        def submit_post_only_batch(
            self,
            orders: tuple[HyperliquidPostOnlyOrder, ...],
        ) -> tuple[HyperliquidOrderAck, ...]:
            acknowledgements = super().submit_post_only_batch(orders)
            clock.advance(900)
            return acknowledgements

    venue = _SlowBatchAckVenue()
    telemetry = _Telemetry()

    snapshot = _engine(venue, telemetry, clock).start()

    assert snapshot.state is ApexMMLiveState.QUOTING
    assert snapshot.bid_oid == 1
    assert snapshot.ask_oid == 2
    assert [call[0] for call in venue.calls].count("submit_batch") == 1
    assert len(venue.orders) == 2
    assert not any(call[0] == "cancel" for call in venue.calls)
    assert not any(event == "fault" for event, _ in telemetry.events)


def test_lost_submit_response_recovers_exact_client_identity() -> None:
    venue = _Venue()
    venue.transport_side = "sell"
    telemetry = _Telemetry()

    snapshot = _engine(venue, telemetry, _Clock()).start()

    assert snapshot.state is ApexMMLiveState.QUOTING
    assert snapshot.bid_oid == 1
    assert snapshot.ask_oid == 2
    intents = [
        payload for event, payload in telemetry.events if event == "order_intent"
    ]
    assert all("client_order_id" in payload for payload in intents)
    recovered = [
        payload for event, payload in telemetry.events if event == "quote_sell"
    ]
    assert recovered[0].recovered_after_transport_error


def test_lost_cancel_response_recovers_exact_oid_then_requotes() -> None:
    venue = _Venue()
    clock = _Clock()
    engine = _engine(venue, _Telemetry(), clock)
    initial = engine.start()
    venue.transport_cancel_oid = initial.bid_oid
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = _book(
        int(clock.now.timestamp() * 1_000),
        best_bid=100.1,
        best_ask=101.1,
    )

    refreshed = engine.process()

    assert refreshed.bid_oid == 3
    assert refreshed.ask_oid == 4


def test_cancel_rejection_recovers_exact_fill_race_then_requotes() -> None:
    class _CancelFillRaceVenue(_Venue):
        def __init__(self) -> None:
            super().__init__()
            self.raced = False

        def cancel_order(self, oid: int) -> HyperliquidOrderAck:
            if self.raced:
                return super().cancel_order(oid)
            self.raced = True
            self.calls.append(("cancel", oid))
            self.orders = [order for order in self.orders if order.oid != oid]
            self.status_by_oid[oid] = HyperliquidOrderStatus(
                oid,
                "BTC",
                "filled",
                0.1,
                1_785_586_383_357,
            )
            return HyperliquidOrderAck(False, oid, "error", error="already filled")

    venue = _CancelFillRaceVenue()
    clock = _Clock()
    engine = _engine(venue, _Telemetry(), clock)
    engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = _book(
        int(clock.now.timestamp() * 1_000),
        best_bid=100.1,
        best_ask=101.1,
    )

    refreshed = engine.process()

    assert refreshed.state is ApexMMLiveState.QUOTING
    assert refreshed.bid_oid == 3
    assert refreshed.ask_oid == 4


def test_true_open_cancel_rejection_is_journaled_as_fault() -> None:
    class _OpenCancelRejectVenue(_Venue):
        def cancel_order(self, oid: int) -> HyperliquidOrderAck:
            self.calls.append(("cancel", oid))
            return HyperliquidOrderAck(False, oid, "error", error="still open")

    venue = _OpenCancelRejectVenue()
    telemetry = _Telemetry()
    clock = _Clock()
    engine = _engine(venue, telemetry, clock)
    engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = _book(
        int(clock.now.timestamp() * 1_000),
        best_bid=100.1,
        best_ask=101.1,
    )

    snapshot = engine.process()

    assert snapshot.state is ApexMMLiveState.FAULT
    assert (
        "fault",
        "quote cancel rejected for oid 1",
    ) in telemetry.events


def test_refresh_cancels_both_quotes_before_replacement() -> None:
    venue = _Venue()
    clock = _Clock()
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, clock)
    engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = _book(
        int(clock.now.timestamp() * 1_000),
        best_bid=100.1,
        best_ask=101.1,
    )

    snapshot = engine.process()

    operations = [call[0] for call in venue.calls]
    assert operations == [
        "leverage",
        "submit_batch",
        "funding",
        "cancel",
        "cancel",
        "submit_batch",
    ]
    assert snapshot.bid_oid == 3
    assert snapshot.ask_oid == 4
    intents = [
        payload for event, payload in telemetry.events if event == "order_intent"
    ]
    canceled_oids = {
        payload["oid"]
        for payload in intents
        if payload.get("operation") == "cancel_quote"
    }
    assert canceled_oids == {1, 2}


def test_unchanged_quote_is_observed_without_cancel_replace_churn() -> None:
    venue = _Venue()
    clock = _Clock()
    engine = _engine(venue, _Telemetry(), clock)
    initial = engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = _book(int(clock.now.timestamp() * 1_000))

    observed = engine.process()

    assert observed.bid_oid == initial.bid_oid
    assert observed.ask_oid == initial.ask_oid
    assert [call[0] for call in venue.calls].count("submit_batch") == 1
    assert [call[0] for call in venue.calls].count("cancel") == 0


def test_funding_history_is_polled_once_per_hour_not_once_per_tick() -> None:
    venue = _Venue()
    clock = _Clock()
    engine = _engine(venue, _Telemetry(), clock)
    engine.start()
    for _ in range(2):
        clock.advance(_QUOTE_REFRESH_MS + 1)
        venue.book = _book(int(clock.now.timestamp() * 1_000))
        engine.process()

    assert [call[0] for call in venue.calls].count("funding") == 1

    clock.advance(3_600_000)
    venue.book = _book(int(clock.now.timestamp() * 1_000))
    engine.process()

    assert [call[0] for call in venue.calls].count("funding") == 2


def test_known_venue_schema_error_is_logged_as_fault_before_cleanup() -> None:
    class _MalformedStreamVenue(_Venue):
        def __init__(self) -> None:
            super().__init__()
            self.fail_reconciliation = False

        def reconcile(self) -> SolReconciliationSnapshot:
            if self.fail_reconciliation:
                raise HyperliquidAdapterError("userFills isSnapshot must be boolean")
            return super().reconcile()

        def begin_shutdown(self) -> None:
            self.fail_reconciliation = False
            super().begin_shutdown()

    venue = _MalformedStreamVenue()
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, _Clock())
    engine.start()
    venue.fail_reconciliation = True

    fault = engine.process()
    stopped = engine.shutdown()

    assert fault.state is ApexMMLiveState.FAULT
    assert stopped.state is ApexMMLiveState.STOPPED
    assert (
        "fault",
        "venue state failure: userFills isSnapshot must be boolean",
    ) in telemetry.events
    assert venue.orders == []


def test_inventory_cap_breach_cancels_quotes_flattens_and_faults() -> None:
    venue = _Venue()
    engine = _engine(venue, _Telemetry(), _Clock())
    engine.start()
    venue.account = _account(_position(0.31))

    snapshot = engine.process()

    assert snapshot.state is ApexMMLiveState.FAULT
    assert venue.account.position.size_signed == 0.0
    assert venue.orders == []
    assert any(call[0] == "close" for call in venue.calls)


def test_operator_shutdown_cancels_and_verifies_flat() -> None:
    venue = _Venue()
    engine = _engine(venue, _Telemetry(), _Clock())
    engine.start()
    venue.account = _account(_position(-0.1))

    snapshot = engine.shutdown()

    assert snapshot.state is ApexMMLiveState.STOPPED
    assert venue.orders == []
    assert venue.account.position.size_signed == 0.0


def test_operator_shutdown_journals_exact_cleanup_fill_before_stopped() -> None:
    class _DelayedCleanupFillVenue(_Venue):
        def __init__(self) -> None:
            super().__init__()
            self.waited_fill_oids: list[int] = []

        def wait_for_fill(
            self,
            oid: int,
            markout_horizon_ms: int,
        ) -> tuple[SolReconciliationSnapshot, SolBookSnapshot]:
            assert markout_horizon_ms == 1_000
            self.waited_fill_oids.append(oid)
            fill = SolFill(
                oid,
                100.0,
                0.1,
                "B",
                1_725_000_000_100,
                0.0045,
                "USDC",
                0.0,
                True,
                "Close Short",
                "0xcleanup",
                9_002,
            )
            venue = SolReconciliationSnapshot(self.account, tuple(self.orders), (fill,))
            return venue, self.book

    venue = _DelayedCleanupFillVenue()
    telemetry = _Telemetry()
    engine = _engine(venue, telemetry, _Clock())
    engine.start()
    venue.account = _account(_position(-0.1))

    snapshot = engine.shutdown()

    assert snapshot.state is ApexMMLiveState.STOPPED
    assert venue.waited_fill_oids == [99]
    reconciliations = [
        value for event, value in telemetry.events if event == "reconciliation"
    ]
    assert any(item.fills and item.fills[0].oid == 99 for item in reconciliations)
    cleanup_index = next(
        index
        for index, (event, value) in enumerate(telemetry.events)
        if event == "reconciliation" and value.fills
    )
    assert any(event == "book" for event, _ in telemetry.events[cleanup_index + 1 :])


def test_start_refuses_preexisting_position_or_order() -> None:
    venue = _Venue()
    venue.account = _account(_position(0.1))

    with pytest.raises(ApexMMLiveEngineError, match="flat account"):
        _engine(venue, _Telemetry(), _Clock()).start()

    venue.account = _account()
    venue.orders.append(
        SolOpenOrder(1, 0.1, 0.1, "B", False, False, None, "Limit", 1_000, 100.0)
    )
    with pytest.raises(ApexMMLiveEngineError, match="flat account"):
        _engine(venue, _Telemetry(), _Clock()).start()


def test_stale_book_cancels_quotes_without_replacing_them() -> None:
    venue = _Venue()
    clock = _Clock()
    engine = _engine(venue, _Telemetry(), clock)
    engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)

    snapshot = engine.process()

    assert snapshot.state is ApexMMLiveState.QUOTING
    assert snapshot.bid_oid is None
    assert snapshot.ask_oid is None
    assert venue.orders == []
    assert [call[0] for call in venue.calls].count("submit_batch") == 1


def test_live_cascade_reduces_exposure_increasing_quote_size() -> None:
    venue = _Venue()
    telemetry = _Telemetry()
    clock = _Clock()
    engine = _engine(venue, telemetry, clock)
    engine.start()
    clock.advance(_QUOTE_REFRESH_MS + 1)
    venue.book = SolBookSnapshot(
        int(clock.now.timestamp() * 1_000),
        (SolBookLevel(99.7, 2.0, 1),),
        (SolBookLevel(99.8, 2.0, 1),),
        99.75,
        10.025,
        2.0,
        2.0,
        0.0,
    )

    engine.process()

    latest_quote = [event for event in telemetry.events if event[0] == "quote"][-1]
    quote = latest_quote[1][0]
    assert quote.bid_size == 0.0
    assert quote.ask_size == pytest.approx(12.5 / 99.75, rel=1e-6)
