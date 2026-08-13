"""Deterministic tests for the Apex MM private venue-state stream."""

from __future__ import annotations

import json

import pytest

from hypervector.data.hl_ws_feed import FeedDisconnect, ReceivedMessage
from hypervector.live.apex_mm_venue_stream import (
    ApexMMVenueStream,
    ApexMMVenueStreamError,
    apex_mm_subscription_payloads,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError


_ADDRESS = "0x1111111111111111111111111111111111111111"


class _Feed:
    def __init__(self, messages: tuple[ReceivedMessage | FeedDisconnect, ...]) -> None:
        self.messages = list(messages)
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def wait_for_item(self, *, timeout_seconds: float) -> bool:
        assert timeout_seconds >= 0.0
        return bool(self.messages)

    def drain(self) -> tuple[ReceivedMessage | FeedDisconnect, ...]:
        result = tuple(self.messages)
        self.messages.clear()
        return result

    def close(self) -> None:
        self.closed = True


def _message(
    channel: str, data: object, *, received_ns: int = 1_000_000_000
) -> ReceivedMessage:
    return ReceivedMessage(
        payload=json.dumps({"channel": channel, "data": data}),
        received_ts_ns=received_ns,
    )


def _initial_messages() -> tuple[ReceivedMessage, ...]:
    perp_state = {
        "marginSummary": {
            "accountValue": "153.61",
            "totalMarginUsed": "0",
            "totalNtlPos": "0",
        },
        "withdrawable": "153.61",
        "assetPositions": [],
    }
    spot_state = {
        "balances": [{"coin": "USDC", "total": "153.61", "hold": "0"}],
        "tokenToAvailableAfterMaintenance": [],
    }
    order = {
        "coin": "BTC",
        "oid": 41,
        "sz": "0.1",
        "origSz": "0.1",
        "side": "B",
        "reduceOnly": False,
        "isTrigger": False,
        "triggerPx": "0.0",
        "orderType": "Limit",
        "timestamp": 1_725_000_000_000,
        "limitPx": "100.0",
    }
    fill = {
        "coin": "BTC",
        "oid": 40,
        "px": "100.0",
        "sz": "0.01",
        "side": "B",
        "time": 1_725_000_000_000,
        "fee": "-0.00015",
        "feeToken": "USDC",
        "closedPnl": "0",
        "crossed": False,
        "dir": "Open Long",
        "hash": "0xabc",
        "tid": 1_001,
    }
    return (
        _message(
            "l2Book",
            {
                "coin": "BTC",
                "time": 1_725_000_000_000,
                "levels": [
                    [{"px": "100.0", "sz": "2.0", "n": 1}],
                    [{"px": "101.0", "sz": "3.0", "n": 1}],
                ],
            },
        ),
        _message(
            "clearinghouseState",
            {"clearinghouseState": perp_state, "dex": ""},
        ),
        _message("spotState", {"spotState": spot_state}),
        _message("openOrders", {"orders": [order], "dex": ""}),
        _message("userFills", {"fills": [fill], "isSnapshot": True}),
    )


def test_subscription_payloads_cover_required_low_latency_state() -> None:
    payloads = apex_mm_subscription_payloads(symbol="BTC", account_address=_ADDRESS)
    subscriptions = [json.loads(payload)["subscription"] for payload in payloads]

    assert [item["type"] for item in subscriptions] == [
        "l2Book",
        "clearinghouseState",
        "spotState",
        "openOrders",
        "orderUpdates",
        "userFills",
    ]
    assert subscriptions[0]["coin"] == "BTC"
    assert all(item.get("user") == _ADDRESS for item in subscriptions[1:])


def test_stream_builds_fresh_unified_reconciliation_snapshot() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )

    stream.start(timeout_seconds=1.0)
    snapshot = stream.snapshot(maximum_age_ms=1_000)
    stream.close()

    assert feed.started and feed.closed
    assert snapshot.book.mid_price == pytest.approx(100.5)
    assert snapshot.venue.account.account_value_usd == pytest.approx(153.61)
    assert [order.oid for order in snapshot.venue.open_orders] == [41]
    assert [fill.oid for fill in snapshot.venue.fills] == [40]


def test_disconnect_invalidates_all_prior_stream_state() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    feed.messages.append(FeedDisconnect(1_600_000_000, "injected_gap"))

    with pytest.raises(ApexMMVenueStreamError, match="injected_gap"):
        stream.snapshot(maximum_age_ms=1_000)


def test_stale_required_component_fails_closed() -> None:
    stream = ApexMMVenueStream(
        feed=_Feed(_initial_messages()),
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 3_000_000_000,
    )
    stream.start(timeout_seconds=1.0)

    with pytest.raises(ApexMMVenueStreamError, match="stale"):
        stream.snapshot(maximum_age_ms=1_000)

    assert stream.state_snapshot().venue.is_flat is False


def test_fresh_book_wait_consumes_new_l2_after_stale_initial_snapshot() -> None:
    feed = _Feed(_initial_messages())
    now_ns = [3_000_000_000]
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: now_ns[0],
    )
    stream.start(timeout_seconds=1.0)
    fresh = json.loads(str(_initial_messages()[0].payload))
    fresh["data"]["time"] += 1
    feed.messages.append(ReceivedMessage(json.dumps(fresh), 2_500_000_000))

    book = stream.wait_for_fresh_book(
        maximum_age_ms=1_000,
        timeout_seconds=1.0,
    )

    assert book.exchange_timestamp_ms == 1_725_000_000_001


def test_incremental_fill_updates_are_merged_without_duplicates() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    original = _initial_messages()[-1]
    update = json.loads(str(original.payload))
    update["data"]["isSnapshot"] = False
    update["data"]["fills"][0]["oid"] = 42
    update["data"]["fills"][0]["hash"] = "0xdef"
    update["data"]["fills"][0]["tid"] = 1_002
    feed.messages.extend(
        (
            ReceivedMessage(json.dumps(update), 1_100_000_000),
            ReceivedMessage(json.dumps(update), 1_200_000_000),
        )
    )

    snapshot = stream.snapshot(maximum_age_ms=1_000)

    assert [fill.oid for fill in snapshot.venue.fills] == [40, 42]


def test_incremental_fill_without_snapshot_flag_is_merged() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    update = json.loads(str(_initial_messages()[-1].payload))
    del update["data"]["isSnapshot"]
    update["data"]["fills"][0]["oid"] = 42
    update["data"]["fills"][0]["hash"] = "0xdef"
    update["data"]["fills"][0]["tid"] = 1_002
    feed.messages.append(ReceivedMessage(json.dumps(update), 1_100_000_000))

    snapshot = stream.snapshot(maximum_age_ms=1_000)

    assert [fill.oid for fill in snapshot.venue.fills] == [40, 42]


def test_distinct_partial_fills_survive_shared_order_time_and_transaction() -> None:
    """Two venue trade IDs must remain distinct even within one order and block."""
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    first = json.loads(str(_initial_messages()[-1].payload))
    first["data"]["isSnapshot"] = False
    first["data"]["fills"][0]["oid"] = 42
    first["data"]["fills"][0]["hash"] = "0xshared"
    first["data"]["fills"][0]["tid"] = 2_001
    second = json.loads(json.dumps(first))
    second["data"]["fills"][0]["sz"] = "0.02"
    second["data"]["fills"][0]["tid"] = 2_002
    feed.messages.extend(
        (
            ReceivedMessage(json.dumps(first), 1_100_000_000),
            ReceivedMessage(json.dumps(second), 1_200_000_000),
        )
    )

    snapshot = stream.snapshot(maximum_age_ms=1_000)

    assert [fill.trade_id for fill in snapshot.venue.fills] == [1_001, 2_001, 2_002]


def test_wait_for_fill_consumes_incremental_cleanup_fill() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    update = json.loads(str(_initial_messages()[-1].payload))
    update["data"]["isSnapshot"] = False
    update["data"]["fills"][0]["oid"] = 42
    update["data"]["fills"][0]["hash"] = "0xcleanup"
    update["data"]["fills"][0]["tid"] = 1_002
    feed.messages.append(ReceivedMessage(json.dumps(update), 1_100_000_000))

    snapshot = stream.wait_for_fill(oid=42, timeout_seconds=1.0)

    assert [fill.oid for fill in snapshot.venue.fills] == [40, 42]


def test_wait_for_fill_requires_book_at_configured_markout_horizon() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    update = json.loads(str(_initial_messages()[-1].payload))
    update["data"]["isSnapshot"] = False
    update["data"]["fills"][0]["oid"] = 42
    update["data"]["fills"][0]["hash"] = "0xcleanup"
    update["data"]["fills"][0]["tid"] = 1_002
    later_book = json.loads(str(_initial_messages()[0].payload))
    later_book["data"]["time"] = 1_725_000_001_000
    feed.messages.extend(
        (
            ReceivedMessage(json.dumps(update), 1_100_000_000),
            ReceivedMessage(json.dumps(later_book), 1_200_000_000),
        )
    )

    snapshot = stream.wait_for_fill(
        oid=42,
        timeout_seconds=1.0,
        markout_horizon_ms=1_000,
    )

    assert snapshot.book.exchange_timestamp_ms == 1_725_000_001_000


def test_present_non_boolean_snapshot_flag_remains_rejected() -> None:
    messages = list(_initial_messages())
    invalid = json.loads(str(messages[-1].payload))
    invalid["data"]["isSnapshot"] = "false"
    messages[-1] = ReceivedMessage(json.dumps(invalid), 1_100_000_000)
    feed = _Feed(tuple(messages))
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )

    with pytest.raises(HyperliquidAdapterError, match="isSnapshot must be boolean"):
        stream.start(timeout_seconds=1.0)

    assert feed.closed is True


def test_wait_for_open_orders_consumes_mutation_update() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    feed.messages.append(
        _message("openOrders", {"orders": [], "dex": ""}, received_ns=1_100_000_000)
    )

    snapshot = stream.wait_for_open_orders(
        expected_oids=frozenset(),
        timeout_seconds=1.0,
        maximum_age_ms=1_000,
    )

    assert snapshot.venue.open_orders == ()


def test_order_update_removes_canceled_order_from_open_order_projection() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    full_order = json.loads(str(_initial_messages()[3].payload))["data"]["orders"][0]
    current_order = {
        key: full_order[key]
        for key in ("coin", "limitPx", "oid", "origSz", "side", "sz", "timestamp")
    }
    feed.messages.append(
        _message(
            "orderUpdates",
            [
                {
                    "order": current_order,
                    "status": "canceled",
                    "statusTimestamp": 1_725_000_000_100,
                }
            ],
            received_ns=1_100_000_000,
        )
    )

    snapshot = stream.wait_for_open_orders(
        expected_oids=frozenset(),
        timeout_seconds=1.0,
        maximum_age_ms=1_000,
    )

    assert snapshot.venue.open_orders == ()


def test_minimal_open_order_update_projects_apex_quote_contract() -> None:
    feed = _Feed(_initial_messages())
    stream = ApexMMVenueStream(
        feed=feed,
        symbol="BTC",
        account_mode="unifiedAccount",
        depth_levels=5,
        clock_ns=lambda: 1_500_000_000,
    )
    stream.start(timeout_seconds=1.0)
    feed.messages.append(
        _message(
            "orderUpdates",
            [
                {
                    "order": {
                        "coin": "BTC",
                        "limitPx": "99.0",
                        "oid": 42,
                        "origSz": "0.2",
                        "side": "B",
                        "sz": "0.2",
                        "timestamp": 1_725_000_000_100,
                    },
                    "status": "open",
                    "statusTimestamp": 1_725_000_000_100,
                }
            ],
            received_ns=1_100_000_000,
        )
    )

    snapshot = stream.state_snapshot()
    projected = {order.oid: order for order in snapshot.venue.open_orders}[42]

    assert projected.limit_price == pytest.approx(99.0)
    assert projected.reduce_only is False
    assert projected.is_trigger is False
    assert projected.order_type == "Limit"
