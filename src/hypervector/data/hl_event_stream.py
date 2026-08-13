"""Gap-aware buffer joining live Hyperliquid messages to the event archive."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, cast

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
    parse_hl_message,
)

PublicEvent = L2SnapshotEvent | PublicTradeEvent | AssetContextEvent
RecordedEvent = PublicEvent | StreamGap
_DEDUP_CAPACITY = 50_000


@dataclass(frozen=True)
class _PendingGap:
    detected_ts_ns: int
    reason: str
    previous_exchange_ts_ms: int | None


def subscription_messages(symbol: str) -> tuple[str, ...]:
    """Return official public execution and perps-context subscriptions."""
    if not symbol.strip():
        raise ValueError("symbol must be non-empty")
    subscriptions = (
        {"type": "l2Book", "coin": symbol},
        {"type": "trades", "coin": symbol},
        {"type": "activeAssetCtx", "coin": symbol},
    )
    return tuple(
        json.dumps(
            {"method": "subscribe", "subscription": subscription},
            separators=(",", ":"),
            sort_keys=True,
        )
        for subscription in subscriptions
    )


class HyperliquidEventRecorder:
    """Normalize, deduplicate, archive, and buffer public execution evidence."""

    def __init__(
        self,
        *,
        data_root: Path | str,
        symbol: str,
        archive_batch_size: int,
    ) -> None:
        self._symbol = symbol
        self._archive = EventArchive(
            data_root=data_root,
            symbol=symbol,
            batch_size=archive_batch_size,
        )
        self._buffer: list[RecordedEvent] = []
        self._recent_keys: dict[str, None] = {}
        self._last_exchange_ts_ms: int | None = None
        self._pending_gap: _PendingGap | None = None
        self._closed = False

    def record_message(self, payload: str | bytes, received_ts_ns: int) -> int:
        """Normalize one WebSocket message and return accepted event count."""
        if self._closed:
            raise RuntimeError("event recorder is closed")
        message = _json_object(payload)
        parsed = parse_hl_message(message, received_ts_ns=received_ts_ns)
        events = tuple(event for event in parsed if self._accept(event))
        if not events:
            return 0
        exchange_timestamp = _exchange_timestamp(events[0])
        if exchange_timestamp is not None:
            self._materialize_gap(exchange_timestamp)
        self._archive.append(events)
        self._buffer.extend(events)
        exchange_times = tuple(
            timestamp
            for event in events
            if (timestamp := _exchange_timestamp(event)) is not None
        )
        if exchange_times:
            latest = max(exchange_times)
            if self._last_exchange_ts_ms is not None:
                latest = max(latest, self._last_exchange_ts_ms)
            self._last_exchange_ts_ms = latest
        return len(events)

    def declare_disconnect(self, *, detected_ts_ns: int, reason: str) -> None:
        """Retain a reconnect gap until the next exchange timestamp is known."""
        if self._closed:
            raise RuntimeError("event recorder is closed")
        if detected_ts_ns <= 0:
            raise ValueError("detected_ts_ns must be positive")
        if not reason.strip():
            raise ValueError("disconnect reason must be non-empty")
        if self._pending_gap is None:
            self._pending_gap = _PendingGap(
                detected_ts_ns=detected_ts_ns,
                reason=reason,
                previous_exchange_ts_ms=self._last_exchange_ts_ms,
            )

    def drain(self) -> tuple[RecordedEvent, ...]:
        """Drain buffered evidence in causal ingestion order."""
        events = tuple(self._buffer)
        self._buffer.clear()
        return events

    def flush(self) -> None:
        """Persist the currently buffered archive tail without stopping capture."""
        if self._closed:
            raise RuntimeError("event recorder is closed")
        self._archive.flush()

    def close(self) -> None:
        """Flush durable evidence and persist an unresolved terminal gap."""
        if self._closed:
            return
        if self._pending_gap is not None:
            self._materialize_gap(None)
        self._archive.flush()
        self._closed = True

    def _accept(self, event: PublicEvent) -> bool:
        if event.symbol != self._symbol:
            raise ValueError(f"event symbol {event.symbol!r} != {self._symbol!r}")
        key = (
            f"l2:{event.event_key}"
            if isinstance(event, L2SnapshotEvent)
            else f"trade:{event.trade_key}"
            if isinstance(event, PublicTradeEvent)
            else f"context:{event.event_key}"
        )
        if key in self._recent_keys:
            return False
        self._recent_keys[key] = None
        if len(self._recent_keys) > _DEDUP_CAPACITY:
            self._recent_keys.pop(next(iter(self._recent_keys)))
        return True

    def _materialize_gap(self, next_exchange_ts_ms: int | None) -> None:
        pending = self._pending_gap
        if pending is None:
            return
        gap = StreamGap(
            symbol=self._symbol,
            channel="l2Book,trades,activeAssetCtx",
            detected_ts_ns=pending.detected_ts_ns,
            reason=pending.reason,
            previous_exchange_ts_ms=pending.previous_exchange_ts_ms,
            next_exchange_ts_ms=next_exchange_ts_ms,
        )
        self._archive.record_gap(gap)
        self._buffer.append(gap)
        self._pending_gap = None


def _exchange_timestamp(event: PublicEvent) -> int | None:
    """Return genuine venue event time, never a local context receipt time."""
    if isinstance(event, AssetContextEvent):
        return None
    return event.exchange_ts_ms


def _json_object(payload: str | bytes) -> Mapping[str, object]:
    try:
        value: object = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("WebSocket payload must be valid JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("WebSocket payload must be a JSON object")
    return cast(dict[str, object], value)
