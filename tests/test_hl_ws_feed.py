"""Offline tests for the bounded Hyperliquid WebSocket receiver."""

from __future__ import annotations

import threading

from hypervector.data.hl_ws_feed import (
    FeedDisconnect,
    HyperliquidWebSocketFeed,
    ReceivedMessage,
)


class _BlockingConnection:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = threading.Event()
        self.delivered = threading.Event()

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self, timeout: float | None = None) -> str:
        if not self.delivered.is_set():
            self.delivered.set()
            return '{"channel":"subscriptionResponse","data":{}}'
        if not self.closed.wait(timeout):
            raise TimeoutError
        raise OSError("closed")

    def close(self) -> None:
        self.closed.set()


class _SendTimeoutConnection(_BlockingConnection):
    """Connection that times out while the subscription is sent."""

    def send(self, payload: str) -> None:
        raise TimeoutError("subscription send timed out")


def test_feed_subscribes_and_buffers_timestamped_message() -> None:
    connection = _BlockingConnection()

    def connector(_url: str) -> _BlockingConnection:
        return connection

    feed = HyperliquidWebSocketFeed(
        symbol="BTC",
        connector=connector,
        clock_ns=lambda: 123_000_000,
        reconnect_seconds=60.0,
    )

    feed.start()
    assert feed.wait_for_item(timeout_seconds=1.0)
    items = feed.drain()
    feed.close()

    assert len(connection.sent) == 2
    assert '"type":"l2Book"' in connection.sent[0]
    assert '"type":"trades"' in connection.sent[1]
    assert items == (
        ReceivedMessage(
            payload='{"channel":"subscriptionResponse","data":{}}',
            received_ts_ns=123_000_000,
        ),
    )


def test_connection_failure_is_explicit_gap_evidence() -> None:
    attempted = threading.Event()

    def fail(_url: str) -> _BlockingConnection:
        attempted.set()
        raise OSError("offline")

    feed = HyperliquidWebSocketFeed(
        symbol="BTC",
        connector=fail,
        clock_ns=lambda: 456_000_000,
        reconnect_seconds=60.0,
    )

    feed.start()
    assert attempted.wait(1.0)
    assert feed.wait_for_item(timeout_seconds=1.0)
    items = feed.drain()
    feed.close()

    assert items == (
        FeedDisconnect(
            detected_ts_ns=456_000_000,
            reason="websocket_connect_failed:OSError",
        ),
    )


def test_subscription_timeout_is_explicit_gap_evidence() -> None:
    connection = _SendTimeoutConnection()
    feed = HyperliquidWebSocketFeed(
        symbol="BTC",
        connector=lambda _url: connection,
        clock_ns=lambda: 789_000_000,
        reconnect_seconds=60.0,
    )

    feed.start()
    assert feed.wait_for_item(timeout_seconds=1.0)
    items = feed.drain()
    feed.close()

    assert items == (
        FeedDisconnect(
            detected_ts_ns=789_000_000,
            reason="websocket_disconnected:TimeoutError",
        ),
    )
