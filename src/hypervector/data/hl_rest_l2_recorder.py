"""Research-only Hyperliquid REST L2 snapshot recorder."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from hypervector.data.hl_events import L2SnapshotEvent, StreamGap, parse_hl_message

REST_L2_SOURCE = "hyperliquid_rest_l2Book_1s"
REST_L2_CHANNEL = "l2Book_rest_1s"


class HyperliquidInfoProtocol(Protocol):
    """Minimal public information-client boundary used by the recorder."""

    def l2_snapshot(self, name: str) -> object:
        """Return one official-shape public L2 snapshot payload."""


class L2ArchiveProtocol(Protocol):
    """Append-only evidence sink required by the REST recorder."""

    def append(self, events: Iterable[L2SnapshotEvent]) -> None:
        """Append normalized L2 events."""

    def record_gap(self, gap: StreamGap) -> None:
        """Persist an explicit transport uncertainty interval."""

    def flush(self) -> None:
        """Flush buffered evidence to durable storage."""


@dataclass(frozen=True)
class _PendingGap:
    detected_ts_ns: int
    reason: str
    previous_exchange_ts_ms: int | None


class HyperliquidRestL2Recorder:
    """Normalize public REST books and retain transport gaps explicitly."""

    def __init__(
        self,
        *,
        info: HyperliquidInfoProtocol,
        archive: L2ArchiveProtocol,
        symbol: str,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if not symbol or not symbol.isascii() or not symbol.isalnum():
            raise ValueError("symbol must be a non-empty ASCII alphanumeric value")
        self._info = info
        self._archive = archive
        self._symbol = symbol
        self._clock_ns = clock_ns
        self._last_exchange_ts_ms: int | None = None
        self._pending_gap: _PendingGap | None = None

    def poll(self) -> L2SnapshotEvent:
        """Fetch, normalize, label, and append one public book snapshot."""
        payload = self._info.l2_snapshot(self._symbol)
        if not isinstance(payload, Mapping):
            raise ValueError("Hyperliquid l2_snapshot response must be an object")
        received_ts_ns = self._clock_ns()
        message: dict[str, object] = {"channel": "l2Book", "data": payload}
        parsed = parse_hl_message(message, received_ts_ns=received_ts_ns)
        if len(parsed) != 1 or not isinstance(parsed[0], L2SnapshotEvent):
            raise ValueError("Hyperliquid l2_snapshot response was not one L2 book")
        event = replace(parsed[0], source=REST_L2_SOURCE)
        if event.symbol != self._symbol:
            raise ValueError(
                f"REST L2 symbol {event.symbol!r} != requested {self._symbol!r}"
            )
        self._materialize_pending_gap(event.exchange_ts_ms)
        self._archive.append((event,))
        self._last_exchange_ts_ms = event.exchange_ts_ms
        return event

    def declare_gap(self, *, detected_ts_ns: int, reason: str) -> None:
        """Declare a failed polling interval without inventing market events."""
        if detected_ts_ns <= 0:
            raise ValueError("detected_ts_ns must be positive")
        if not reason.strip():
            raise ValueError("gap reason must be non-empty")
        if self._pending_gap is None:
            self._pending_gap = _PendingGap(
                detected_ts_ns=detected_ts_ns,
                reason=reason,
                previous_exchange_ts_ms=self._last_exchange_ts_ms,
            )

    def close(self) -> None:
        """Persist any unresolved terminal gap and flush buffered evidence."""
        if self._pending_gap is not None:
            self._archive.record_gap(self._stream_gap(next_exchange_ts_ms=None))
            self._pending_gap = None
        self._archive.flush()

    def flush(self) -> None:
        """Persist the current archive tail without stopping capture."""
        self._archive.flush()

    def _materialize_pending_gap(self, next_exchange_ts_ms: int) -> None:
        if self._pending_gap is None:
            return
        self._archive.record_gap(
            self._stream_gap(next_exchange_ts_ms=next_exchange_ts_ms)
        )
        self._pending_gap = None

    def _stream_gap(self, *, next_exchange_ts_ms: int | None) -> StreamGap:
        pending = self._pending_gap
        if pending is None:
            raise RuntimeError("no pending REST L2 gap to materialize")
        return StreamGap(
            symbol=self._symbol,
            channel=REST_L2_CHANNEL,
            detected_ts_ns=pending.detected_ts_ns,
            reason=pending.reason,
            previous_exchange_ts_ms=pending.previous_exchange_ts_ms,
            next_exchange_ts_ms=next_exchange_ts_ms,
        )
