"""Bounded public Hyperliquid WebSocket receiver with explicit gaps."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from hypervector.data.hl_event_stream import subscription_messages

MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"


class WebSocketConnection(Protocol):
    """Synchronous connection surface used by the background receiver."""

    def send(self, payload: str) -> None:
        """Send one subscription payload."""

    def recv(self, timeout: float | None = None) -> str | bytes:
        """Receive one frame or raise TimeoutError while idle."""

    def close(self) -> None:
        """Close the socket and unblock a pending receive."""


@dataclass(frozen=True)
class ReceivedMessage:
    """One raw frame stamped at the local transport boundary."""

    payload: str | bytes
    received_ts_ns: int


@dataclass(frozen=True)
class FeedDisconnect:
    """One interval where transport completeness became unknown."""

    detected_ts_ns: int
    reason: str


FeedItem: TypeAlias = ReceivedMessage | FeedDisconnect
Connector: TypeAlias = Callable[[str], WebSocketConnection]


class HyperliquidWebSocketFeed:
    """Receive public L2/trades without blocking the candle scheduler."""

    def __init__(
        self,
        *,
        symbol: str,
        subscription_payloads: tuple[str, ...] | None = None,
        connector: Connector | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
        reconnect_seconds: float = 1.0,
        max_buffered_items: int = 50_000,
    ) -> None:
        if not symbol.strip():
            raise ValueError("symbol must be non-empty")
        if reconnect_seconds <= 0.0:
            raise ValueError("reconnect_seconds must be positive")
        if max_buffered_items <= 1:
            raise ValueError("max_buffered_items must exceed one")
        subscriptions = (
            subscription_messages(symbol)
            if subscription_payloads is None
            else tuple(subscription_payloads)
        )
        if not subscriptions or any(not payload.strip() for payload in subscriptions):
            raise ValueError("subscription_payloads must contain non-empty messages")
        self._symbol = symbol
        self._subscription_payloads = subscriptions
        self._connector = connector or _connect_mainnet
        self._clock_ns = clock_ns
        self._reconnect_seconds = reconnect_seconds
        self._max_buffered_items = max_buffered_items
        self._items: list[FeedItem] = []
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: WebSocketConnection | None = None

    def start(self) -> None:
        """Start exactly one background receiver thread."""
        if self._thread is not None:
            raise RuntimeError("WebSocket feed already started")
        self._thread = threading.Thread(
            target=self._run,
            name=f"hyperliquid-{self._symbol}-events",
            daemon=True,
        )
        self._thread.start()

    def wait_for_item(self, *, timeout_seconds: float) -> bool:
        """Wait until evidence is buffered; primarily useful for readiness tests."""
        if timeout_seconds < 0.0:
            raise ValueError("timeout_seconds must be non-negative")
        with self._condition:
            return self._condition.wait_for(
                lambda: bool(self._items),
                timeout=timeout_seconds,
            )

    def drain(self) -> tuple[FeedItem, ...]:
        """Drain raw messages and disconnect evidence in receive order."""
        thread = self._thread
        if thread is not None and not thread.is_alive() and not self._stop.is_set():
            raise RuntimeError("Hyperliquid WebSocket receiver stopped unexpectedly")
        with self._condition:
            items = tuple(self._items)
            self._items.clear()
        return items

    def close(self) -> None:
        """Stop the receiver and close its current connection."""
        self._stop.set()
        connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                raise RuntimeError("Hyperliquid WebSocket receiver did not stop")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                connection = self._connector(MAINNET_WS_URL)
            except (OSError, TimeoutError, WebSocketException) as exc:
                self._disconnect(f"websocket_connect_failed:{type(exc).__name__}")
                self._stop.wait(self._reconnect_seconds)
                continue
            self._connection = connection
            try:
                self._receive(connection)
            finally:
                self._connection = None
                try:
                    connection.close()
                except OSError:
                    pass

    def _receive(self, connection: WebSocketConnection) -> None:
        try:
            for message in self._subscription_payloads:
                connection.send(message)
            while not self._stop.is_set():
                try:
                    payload = connection.recv(timeout=1.0)
                except TimeoutError:
                    continue
                self._push(
                    ReceivedMessage(
                        payload=payload,
                        received_ts_ns=self._clock_ns(),
                    )
                )
        except (WebSocketException, OSError) as exc:
            if not self._stop.is_set():
                self._disconnect(f"websocket_disconnected:{type(exc).__name__}")
                self._stop.wait(self._reconnect_seconds)

    def _disconnect(self, reason: str) -> None:
        self._push(
            FeedDisconnect(
                detected_ts_ns=self._clock_ns(),
                reason=reason,
            )
        )

    def _push(self, item: FeedItem) -> None:
        with self._condition:
            if len(self._items) >= self._max_buffered_items:
                self._items.clear()
                item = FeedDisconnect(
                    detected_ts_ns=self._clock_ns(),
                    reason="websocket_buffer_overflow",
                )
            self._items.append(item)
            self._condition.notify_all()


def _connect_mainnet(url: str) -> WebSocketConnection:
    """Open the official mainnet public WebSocket endpoint."""
    return connect(url, open_timeout=10.0, close_timeout=2.0)
