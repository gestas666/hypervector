"""Join the live public WebSocket feed to archive and shadow execution."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hypervector.data.hl_event_stream import HyperliquidEventRecorder, RecordedEvent
from hypervector.data.hl_events import StreamGap
from hypervector.data.hl_ws_feed import (
    FeedDisconnect,
    FeedItem,
    HyperliquidWebSocketFeed,
    ReceivedMessage,
)


class EventFeed(Protocol):
    """Transport surface required by the event stream pump."""

    def start(self) -> None:
        """Start receiving public messages."""

    def drain(self) -> tuple[FeedItem, ...]:
        """Drain received frames and disconnect declarations."""

    def close(self) -> None:
        """Stop receiving messages."""


class EventConsumer(Protocol):
    """Backend session surface that consumes normalized venue evidence."""

    def ingest_hyperliquid_event(self, event: RecordedEvent) -> str | None:
        """Apply one normalized public event to backend state."""


class EventStreamPump(Protocol):
    """Lifecycle surface injected into the backend daemon."""

    def start(self) -> None:
        """Start public event capture."""

    def pump(self, consumer: EventConsumer) -> int:
        """Deliver currently buffered public evidence."""

    def close(self) -> None:
        """Stop capture and flush durable evidence."""


class HypervelocityEventStreamPump:
    """Archive public evidence before routing it to shadow execution."""

    def __init__(
        self,
        *,
        data_root: Path | str,
        symbol: str,
        archive_batch_size: int = 2_000,
        feed: EventFeed | None = None,
    ) -> None:
        self._symbol = symbol
        self._feed = feed or HyperliquidWebSocketFeed(symbol=symbol)
        self._recorder = HyperliquidEventRecorder(
            data_root=data_root,
            symbol=symbol,
            archive_batch_size=archive_batch_size,
        )
        self._started = False
        self._closed = False

    def start(self) -> None:
        """Start the transport once."""
        if self._started:
            raise RuntimeError("event stream pump already started")
        self._feed.start()
        self._started = True

    def pump(self, consumer: EventConsumer) -> int:
        """Archive and deliver every currently buffered item in causal order."""
        if not self._started or self._closed:
            raise RuntimeError("event stream pump is not active")
        delivered = 0
        for item in self._feed.drain():
            if isinstance(item, FeedDisconnect):
                self._declare_disconnect(item, consumer)
                delivered += 1
                continue
            if not isinstance(item, ReceivedMessage):
                raise TypeError(f"unsupported feed item {type(item).__name__}")
            self._recorder.record_message(item.payload, item.received_ts_ns)
            for event in self._recorder.drain():
                consumer.ingest_hyperliquid_event(event)
                delivered += 1
        return delivered

    def close(self) -> None:
        """Stop transport and durably flush buffered archive evidence."""
        if self._closed:
            return
        self._feed.close()
        self._recorder.close()
        self._closed = True

    def _declare_disconnect(
        self,
        item: FeedDisconnect,
        consumer: EventConsumer,
    ) -> None:
        self._recorder.declare_disconnect(
            detected_ts_ns=item.detected_ts_ns,
            reason=item.reason,
        )
        consumer.ingest_hyperliquid_event(
            StreamGap(
                symbol=self._symbol,
                channel="l2Book,trades",
                detected_ts_ns=item.detected_ts_ns,
                reason=item.reason,
                previous_exchange_ts_ms=None,
                next_exchange_ts_ms=None,
            )
        )
