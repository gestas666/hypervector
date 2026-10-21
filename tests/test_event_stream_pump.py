"""Event transport-to-session integration without network calls."""

from __future__ import annotations

from pathlib import Path

from hypervector.data.hl_events import L2SnapshotEvent, StreamGap
from hypervector.data.hl_ws_feed import FeedDisconnect, ReceivedMessage
from hypervector.paper.event_stream_pump import HyperliquidEventStreamPump


FIXTURES = Path("tests/fixtures")


class _Feed:
    def __init__(self, items: tuple[FeedDisconnect | ReceivedMessage, ...]) -> None:
        self.items = items
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def drain(self) -> tuple[FeedDisconnect | ReceivedMessage, ...]:
        items = self.items
        self.items = ()
        return items

    def close(self) -> None:
        self.closed = True


class _Consumer:
    def __init__(self) -> None:
        self.events: list[L2SnapshotEvent | StreamGap] = []

    def ingest_hyperliquid_event(
        self,
        event: L2SnapshotEvent | StreamGap,
    ) -> str | None:
        self.events.append(event)
        return None


def test_pump_declares_gap_then_archives_and_delivers_reconnected_event(
    tmp_path: Path,
) -> None:
    payload = (FIXTURES / "hl_ws_l2_sample.json").read_text(encoding="utf-8")
    feed = _Feed(
        (
            FeedDisconnect(1_785_103_200_100_000_000, "websocket_reconnect"),
            ReceivedMessage(payload, 1_785_103_200_300_000_000),
        )
    )
    pump = HyperliquidEventStreamPump(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
        feed=feed,
    )
    consumer = _Consumer()

    pump.start()
    delivered = pump.pump(consumer)
    pump.close()

    assert delivered == 3
    assert feed.started and feed.closed
    assert isinstance(consumer.events[0], StreamGap)
    assert isinstance(consumer.events[1], StreamGap)
    assert isinstance(consumer.events[2], L2SnapshotEvent)
    assert consumer.events[1].next_exchange_ts_ms == 1_785_103_200_000
