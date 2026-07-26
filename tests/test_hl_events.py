"""Hyperliquid public event parsing and append-only archive tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import (
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
    parse_hl_message,
)

FIXTURES = Path("tests/fixtures")
RECEIVED_NS = 1_785_103_200_300_000_000


def fixture(name: str) -> dict[str, object]:
    """Load one sanitized official-shape WebSocket fixture."""
    value: object = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def l2_event() -> L2SnapshotEvent:
    """Parse and return the fixture L2 snapshot."""
    events = parse_hl_message(
        fixture("hl_ws_l2_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, L2SnapshotEvent)
    return event


def trade_events() -> tuple[PublicTradeEvent, ...]:
    """Parse and return the fixture public trades."""
    events = parse_hl_message(
        fixture("hl_ws_trades_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )
    assert all(isinstance(event, PublicTradeEvent) for event in events)
    return tuple(event for event in events if isinstance(event, PublicTradeEvent))


def test_parse_l2_snapshot_preserves_exchange_and_receive_time() -> None:
    event = l2_event()

    assert event.symbol == "BTC"
    assert event.exchange_ts_ms == 1_785_103_200_000
    assert event.received_ts_ns == RECEIVED_NS
    assert [(level.price, level.size, level.order_count) for level in event.bids] == [
        (64_500.0, 1.25, 3),
        (64_499.0, 0.5, 1),
    ]
    assert event.asks[0].price == pytest.approx(64_501.0)


def test_parse_public_trades_uses_venue_global_identity() -> None:
    buy, sell = trade_events()

    assert buy.aggressor_side == "buy"
    assert sell.aggressor_side == "sell"
    assert buy.trade_key == "1785103200100:BTC:987654321"
    assert buy.exchange_ts_ms * 1_000_000 < buy.received_ts_ns


def test_parser_rejects_invalid_price() -> None:
    message = fixture("hl_ws_l2_sample.json")
    data = message["data"]
    assert isinstance(data, dict)
    levels = data["levels"]
    assert isinstance(levels, list)
    bids = levels[0]
    assert isinstance(bids, list)
    first = bids[0]
    assert isinstance(first, dict)
    first["px"] = "nan"

    with pytest.raises(ValueError, match="price"):
        parse_hl_message(message, received_ts_ns=RECEIVED_NS)


def test_archive_deduplicates_and_replays_append_only_parts(tmp_path: Path) -> None:
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=2)
    book = l2_event()
    duplicate_book = replace(book, received_ts_ns=book.received_ts_ns + 1)
    trades = trade_events()

    archive.append((book, duplicate_book, *trades, trades[0]))
    archive.flush()

    assert archive.replay_l2() == (book,)
    assert archive.replay_trades() == trades
    day = book.utc_date
    root = tmp_path / "cache" / "events" / "hyperliquid" / "BTC" / day
    assert list((root / "l2.parquet").glob("part-*.parquet"))
    assert list((root / "trades.parquet").glob("part-*.parquet"))


def test_archive_rotates_by_exchange_utc_day(tmp_path: Path) -> None:
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    first = l2_event()
    next_day = replace(first, exchange_ts_ms=first.exchange_ts_ms + 86_400_000)

    archive.append((first, next_day))
    archive.flush()

    assert first.utc_date != next_day.utc_date
    for day in (first.utc_date, next_day.utc_date):
        directory = (
            tmp_path / "cache" / "events" / "hyperliquid" / "BTC" / day / "l2.parquet"
        )
        assert list(directory.glob("part-*.parquet"))


def test_archive_records_reconnect_gap_without_fabricating_events(
    tmp_path: Path,
) -> None:
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    gap = StreamGap(
        symbol="BTC",
        channel="l2Book",
        detected_ts_ns=RECEIVED_NS,
        reason="websocket_reconnect",
        previous_exchange_ts_ms=1_785_103_199_000,
        next_exchange_ts_ms=1_785_103_200_000,
    )

    archive.record_gap(gap)

    assert archive.replay_gaps() == (gap,)
    gap_file = (
        tmp_path
        / "cache"
        / "events"
        / "hyperliquid"
        / "BTC"
        / gap.utc_date
        / "gaps.jsonl"
    )
    assert gap_file.is_file()
