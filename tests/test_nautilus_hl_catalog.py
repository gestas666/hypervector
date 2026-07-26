"""Round-trip normalized Hyperliquid events through a Nautilus catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nautilus_trader.model.data import OrderBookDelta, QuoteTick, TradeTick
from nautilus_trader.model.enums import BookAction, RecordFlag
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import (
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
    parse_hl_message,
)
from hypervector.nautilus.hl_catalog import (
    convert_hyperliquid_events,
    write_hyperliquid_catalog,
)

FIXTURES = Path("tests/fixtures")
RECEIVED_NS = 1_785_103_200_300_000_000
INSTRUMENT_ID = "BTC-PERP.HYPERLIQUID"


def _fixture(name: str) -> dict[str, object]:
    value: object = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _events() -> tuple[L2SnapshotEvent, tuple[PublicTradeEvent, ...]]:
    books = parse_hl_message(
        _fixture("hl_ws_l2_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )
    trades = parse_hl_message(
        _fixture("hl_ws_trades_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )
    book = books[0]
    assert isinstance(book, L2SnapshotEvent)
    public_trades = tuple(
        event for event in trades if isinstance(event, PublicTradeEvent)
    )
    return book, public_trades


def test_conversion_preserves_snapshot_flags_and_timestamps() -> None:
    book, trades = _events()

    converted = convert_hyperliquid_events(
        l2_events=(book,),
        trade_events=trades,
        instrument_id=INSTRUMENT_ID,
        price_precision=1,
        size_precision=5,
    )

    assert len(converted.book_deltas) == 5
    assert converted.book_deltas[0].action == BookAction.CLEAR
    assert converted.book_deltas[0].sequence == 0
    assert all(
        delta.flags & int(RecordFlag.F_SNAPSHOT) for delta in converted.book_deltas
    )
    assert converted.book_deltas[-1].flags & int(RecordFlag.F_LAST)
    assert converted.book_deltas[0].ts_event == book.exchange_ts_ms * 1_000_000
    assert converted.book_deltas[0].ts_init == book.received_ts_ns
    assert converted.quotes[0].bid_price.as_double() == pytest.approx(64_500.0)
    assert converted.quotes[0].ask_price.as_double() == pytest.approx(64_501.0)
    assert converted.trades[0].ts_event == trades[0].exchange_ts_ms * 1_000_000
    assert str(converted.trades[0].trade_id) == trades[0].trade_key


def test_catalog_round_trip_preserves_events_and_gap_provenance(tmp_path: Path) -> None:
    book, trades = _events()
    archive = EventArchive(data_root=tmp_path / "data", symbol="BTC", batch_size=10)
    archive.append((book, *trades))
    archive.flush()
    gap = StreamGap(
        symbol="BTC",
        channel="trades",
        detected_ts_ns=RECEIVED_NS + 1,
        reason="websocket_reconnect",
        previous_exchange_ts_ms=trades[0].exchange_ts_ms,
        next_exchange_ts_ms=trades[1].exchange_ts_ms,
    )
    archive.record_gap(gap)
    catalog_path = tmp_path / "catalog"

    result = write_hyperliquid_catalog(
        archive=archive,
        catalog_path=catalog_path,
        instrument_id=INSTRUMENT_ID,
        price_precision=1,
        size_precision=5,
    )

    catalog = ParquetDataCatalog(str(catalog_path.resolve()))
    deltas = catalog.query(OrderBookDelta, identifiers=[INSTRUMENT_ID])
    quotes = catalog.query(QuoteTick, identifiers=[INSTRUMENT_ID])
    matches = catalog.query(TradeTick, identifiers=[INSTRUMENT_ID])
    assert len(deltas) == 5
    assert len(quotes) == 1
    assert len(matches) == 2
    assert result.book_delta_count == 5
    assert result.trade_count == 2
    assert result.gap_count == 1
    gap_rows = [
        json.loads(line)
        for line in result.gap_provenance_path.read_text(encoding="utf-8").splitlines()
    ]
    assert gap_rows == [
        {
            "channel": "trades",
            "detected_ts_ns": RECEIVED_NS + 1,
            "next_exchange_ts_ms": trades[1].exchange_ts_ms,
            "previous_exchange_ts_ms": trades[0].exchange_ts_ms,
            "reason": "websocket_reconnect",
            "symbol": "BTC",
        }
    ]
