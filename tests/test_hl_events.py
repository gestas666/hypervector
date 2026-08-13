"""Hyperliquid public event parsing and append-only archive tests."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.data.event_archive import EventArchive, _trade_from_row
from hypervector.data.hl_events import (
    AssetContextEvent,
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


def test_parse_active_asset_context_declares_local_receive_timestamp() -> None:
    events = parse_hl_message(
        fixture("hl_ws_active_asset_ctx_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AssetContextEvent)
    assert event.symbol == "BTC"
    assert event.observed_ts_ms == RECEIVED_NS // 1_000_000
    assert event.timestamp_source == "local_receive_no_exchange_timestamp"
    assert event.mark_price == pytest.approx(65_159.0)
    assert event.oracle_price == pytest.approx(65_182.0)
    assert event.funding_rate_hourly == pytest.approx(0.0000125)
    assert event.open_interest == pytest.approx(36_677.63364)
    assert event.mid_price == pytest.approx(65_152.5)


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


def test_archive_replay_rejects_corrupt_trade_side() -> None:
    row: dict[str, object] = asdict(trade_events()[0])
    row["aggressor_side"] = "unknown"

    with pytest.raises(ValueError, match="aggressor_side"):
        _trade_from_row(row)


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


def test_archive_supports_an_explicit_safe_transport_namespace(tmp_path: Path) -> None:
    """A REST research feed cannot mix silently with WebSocket evidence."""
    archive = EventArchive(
        data_root=tmp_path,
        symbol="BTC",
        batch_size=2,
        namespace="hyperliquid_rest_1s",
    )
    archive.append((l2_event(),))
    archive.flush()

    root = (
        tmp_path
        / "cache"
        / "events"
        / "hyperliquid_rest_1s"
        / "BTC"
        / l2_event().utc_date
    )
    assert list((root / "l2.parquet").glob("part-*.parquet"))

    with pytest.raises(ValueError, match="namespace"):
        EventArchive(
            data_root=tmp_path,
            symbol="BTC",
            batch_size=2,
            namespace="../unsafe",
        )


def test_archive_round_trips_asset_context_without_invented_exchange_time(
    tmp_path: Path,
) -> None:
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    parsed = parse_hl_message(
        fixture("hl_ws_active_asset_ctx_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )
    context = parsed[0]
    assert isinstance(context, AssetContextEvent)

    archive.append((context,))
    archive.flush()

    assert archive.replay_asset_contexts() == (context,)
    directory = (
        tmp_path
        / "cache"
        / "events"
        / "hyperliquid"
        / "BTC"
        / context.utc_date
        / "asset_context.parquet"
    )
    assert list(directory.glob("part-*.parquet"))


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


def test_archive_replays_only_a_bounded_cross_channel_window(tmp_path: Path) -> None:
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    book = l2_event()
    trade = trade_events()[0]
    context = parse_hl_message(
        fixture("hl_ws_active_asset_ctx_sample.json"),
        received_ts_ns=RECEIVED_NS,
    )[0]
    assert isinstance(context, AssetContextEvent)
    later = replace(book, exchange_ts_ms=book.exchange_ts_ms + 86_400_000)
    gap = StreamGap(
        "BTC",
        "l2Book,trades,activeAssetCtx",
        RECEIVED_NS,
        "test",
        book.exchange_ts_ms - 1,
        book.exchange_ts_ms,
    )
    archive.append((book, trade, context, later))
    archive.record_gap(gap)
    archive.flush()
    start = datetime.fromtimestamp((book.exchange_ts_ms - 1) / 1_000, tz=UTC)
    end = datetime.fromtimestamp((book.exchange_ts_ms + 1_000) / 1_000, tz=UTC)

    replay = archive.replay_window(start, end)

    assert book in replay
    assert trade in replay
    assert context in replay
    assert gap in replay
    assert later not in replay
