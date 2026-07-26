"""Convert archived Hyperliquid public events into Nautilus catalog data."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from nautilus_trader.model.data import (
    BookOrder,
    OrderBookDelta,
    QuoteTick,
    TradeTick,
)
from nautilus_trader.model.enums import (
    AggressorSide,
    BookAction,
    OrderSide,
    RecordFlag,
)
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent, StreamGap


@dataclass(frozen=True)
class ConvertedHyperliquidEvents:
    """Nautilus-native market data generated from normalized venue evidence."""

    book_deltas: tuple[OrderBookDelta, ...]
    quotes: tuple[QuoteTick, ...]
    trades: tuple[TradeTick, ...]


@dataclass(frozen=True)
class CatalogWriteResult:
    """Counts and provenance path from one catalog conversion."""

    book_delta_count: int
    quote_count: int
    trade_count: int
    gap_count: int
    gap_provenance_path: Path


def convert_hyperliquid_events(
    *,
    l2_events: tuple[L2SnapshotEvent, ...],
    trade_events: tuple[PublicTradeEvent, ...],
    instrument_id: str,
    price_precision: int,
    size_precision: int,
) -> ConvertedHyperliquidEvents:
    """Convert normalized snapshots and matches into Nautilus-native objects."""
    instrument = InstrumentId.from_str(instrument_id)
    deltas: list[OrderBookDelta] = []
    quotes: list[QuoteTick] = []
    for snapshot in l2_events:
        snapshot_deltas = _snapshot_deltas(
            snapshot,
            instrument=instrument,
            price_precision=price_precision,
            size_precision=size_precision,
        )
        deltas.extend(snapshot_deltas)
        quotes.append(
            _quote(
                snapshot,
                instrument=instrument,
                price_precision=price_precision,
                size_precision=size_precision,
            )
        )
    trades = tuple(
        _trade(
            event,
            instrument=instrument,
            price_precision=price_precision,
            size_precision=size_precision,
        )
        for event in trade_events
    )
    return ConvertedHyperliquidEvents(
        book_deltas=tuple(deltas),
        quotes=tuple(quotes),
        trades=trades,
    )


def write_hyperliquid_catalog(
    *,
    archive: EventArchive,
    catalog_path: Path | str,
    instrument_id: str,
    price_precision: int,
    size_precision: int,
) -> CatalogWriteResult:
    """Write archived market evidence and explicit gaps into one catalog root."""
    root = Path(catalog_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    converted = convert_hyperliquid_events(
        l2_events=archive.replay_l2(),
        trade_events=archive.replay_trades(),
        instrument_id=instrument_id,
        price_precision=price_precision,
        size_precision=size_precision,
    )
    catalog = ParquetDataCatalog(str(root))
    for data in (converted.book_deltas, converted.quotes, converted.trades):
        if data:
            catalog.write_data(list(data))
    gaps = archive.replay_gaps()
    gap_path = _write_gap_provenance(root, gaps)
    return CatalogWriteResult(
        book_delta_count=len(converted.book_deltas),
        quote_count=len(converted.quotes),
        trade_count=len(converted.trades),
        gap_count=len(gaps),
        gap_provenance_path=gap_path,
    )


def _snapshot_deltas(
    snapshot: L2SnapshotEvent,
    *,
    instrument: InstrumentId,
    price_precision: int,
    size_precision: int,
) -> tuple[OrderBookDelta, ...]:
    ts_event = snapshot.exchange_ts_ms * 1_000_000
    base_flags = int(RecordFlag.F_SNAPSHOT) | int(RecordFlag.F_MBP)
    rows: list[OrderBookDelta] = [
        OrderBookDelta(
            instrument,
            BookAction.CLEAR,
            None,
            base_flags,
            0,
            ts_event,
            snapshot.received_ts_ns,
        )
    ]
    levels = (
        *((OrderSide.BUY, level) for level in snapshot.bids),
        *((OrderSide.SELL, level) for level in snapshot.asks),
    )
    for index, (side, level) in enumerate(levels):
        flags = base_flags
        if index == len(levels) - 1:
            flags |= int(RecordFlag.F_LAST)
        order = BookOrder(
            side,
            Price(level.price, price_precision),
            Quantity(level.size, size_precision),
            0,
        )
        rows.append(
            OrderBookDelta(
                instrument,
                BookAction.ADD,
                order,
                flags,
                0,
                ts_event,
                snapshot.received_ts_ns,
            )
        )
    return tuple(rows)


def _quote(
    snapshot: L2SnapshotEvent,
    *,
    instrument: InstrumentId,
    price_precision: int,
    size_precision: int,
) -> QuoteTick:
    bid = snapshot.bids[0]
    ask = snapshot.asks[0]
    return QuoteTick(
        instrument,
        Price(bid.price, price_precision),
        Price(ask.price, price_precision),
        Quantity(bid.size, size_precision),
        Quantity(ask.size, size_precision),
        snapshot.exchange_ts_ms * 1_000_000,
        snapshot.received_ts_ns,
    )


def _trade(
    event: PublicTradeEvent,
    *,
    instrument: InstrumentId,
    price_precision: int,
    size_precision: int,
) -> TradeTick:
    aggressor = (
        AggressorSide.BUYER if event.aggressor_side == "buy" else AggressorSide.SELLER
    )
    return TradeTick(
        instrument,
        Price(event.price, price_precision),
        Quantity(event.size, size_precision),
        aggressor,
        TradeId(event.trade_key),
        event.exchange_ts_ms * 1_000_000,
        event.received_ts_ns,
    )


def _write_gap_provenance(root: Path, gaps: tuple[StreamGap, ...]) -> Path:
    directory = root / "provenance"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"hyperliquid-gaps-{uuid4().hex}.jsonl"
    with path.open("x", encoding="utf-8") as handle:
        for gap in gaps:
            handle.write(json.dumps(asdict(gap), sort_keys=True) + "\n")
    return path
