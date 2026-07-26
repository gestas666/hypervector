"""Bounded append-only Parquet archive for normalized Hyperliquid events."""

from __future__ import annotations

import json
from collections import OrderedDict, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from hypervector.data.hl_events import (
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)

_LEVEL = pa.struct(
    [
        pa.field("price", pa.float64(), nullable=False),
        pa.field("size", pa.float64(), nullable=False),
        pa.field("order_count", pa.int64(), nullable=False),
    ]
)
_L2_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("exchange_ts_ms", pa.int64(), nullable=False),
        pa.field("received_ts_ns", pa.int64(), nullable=False),
        pa.field("bids", pa.list_(_LEVEL), nullable=False),
        pa.field("asks", pa.list_(_LEVEL), nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)
_TRADE_SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("aggressor_side", pa.string(), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("size", pa.float64(), nullable=False),
        pa.field("transaction_hash", pa.string(), nullable=False),
        pa.field("exchange_ts_ms", pa.int64(), nullable=False),
        pa.field("received_ts_ns", pa.int64(), nullable=False),
        pa.field("trade_id", pa.int64(), nullable=False),
        pa.field("buyer", pa.string(), nullable=False),
        pa.field("seller", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
    ]
)


class _RecentKeys:
    """Bound duplicate detection memory while retaining recent venue identities."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._keys: OrderedDict[str, None] = OrderedDict()

    def add_if_new(self, key: str) -> bool:
        """Return false for a recent duplicate and remember a new key."""
        if key in self._keys:
            self._keys.move_to_end(key)
            return False
        self._keys[key] = None
        if len(self._keys) > self._capacity:
            self._keys.popitem(last=False)
        return True


class EventArchive:
    """Buffer, deduplicate, rotate, and replay public event evidence."""

    def __init__(self, *, data_root: Path | str, symbol: str, batch_size: int) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._root = Path(data_root) / "cache" / "events" / "hyperliquid" / symbol
        self._symbol = symbol
        self._batch_size = batch_size
        self._l2: list[L2SnapshotEvent] = []
        self._trades: list[PublicTradeEvent] = []
        dedup_capacity = max(batch_size * 4, 1_024)
        self._seen_l2 = _RecentKeys(dedup_capacity)
        self._seen_trades = _RecentKeys(dedup_capacity)

    def append(
        self,
        events: Iterable[L2SnapshotEvent | PublicTradeEvent],
    ) -> None:
        """Append normalized events, flushing bounded batches atomically."""
        for event in events:
            if event.symbol != self._symbol:
                raise ValueError(f"event symbol {event.symbol!r} != {self._symbol!r}")
            if isinstance(event, L2SnapshotEvent):
                if self._seen_l2.add_if_new(event.event_key):
                    self._l2.append(event)
            elif self._seen_trades.add_if_new(event.trade_key):
                self._trades.append(event)
            if len(self._l2) + len(self._trades) >= self._batch_size:
                self.flush()

    def flush(self) -> None:
        """Write buffered evidence as immutable UTC-day Parquet parts."""
        if self._l2:
            _write_groups(self._root, "l2.parquet", self._l2, _L2_SCHEMA)
            self._l2.clear()
        if self._trades:
            _write_groups(
                self._root,
                "trades.parquet",
                self._trades,
                _TRADE_SCHEMA,
            )
            self._trades.clear()

    def record_gap(self, gap: StreamGap) -> None:
        """Append an explicit event-stream uncertainty interval."""
        if gap.symbol != self._symbol:
            raise ValueError(f"gap symbol {gap.symbol!r} != {self._symbol!r}")
        path = self._root / gap.utc_date / "gaps.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(gap), sort_keys=True) + "\n")

    def replay_l2(self) -> tuple[L2SnapshotEvent, ...]:
        """Return archived L2 snapshots ordered by exchange and receipt time."""
        events = tuple(
            _l2_from_row(row) for row in _read_parts(self._root, "l2.parquet")
        )
        return tuple(
            sorted(
                events, key=lambda event: (event.exchange_ts_ms, event.received_ts_ns)
            )
        )

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        """Return archived trades ordered by exchange time and venue trade ID."""
        events = tuple(
            _trade_from_row(row) for row in _read_parts(self._root, "trades.parquet")
        )
        return tuple(
            sorted(events, key=lambda event: (event.exchange_ts_ms, event.trade_id))
        )

    def replay_gaps(self) -> tuple[StreamGap, ...]:
        """Return declared event gaps ordered by detection time."""
        gaps: list[StreamGap] = []
        for path in sorted(self._root.glob("*/gaps.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    gaps.append(_gap_from_row(_json_object(line)))
        return tuple(sorted(gaps, key=lambda gap: gap.detected_ts_ns))


def _write_groups(
    root: Path,
    dataset: str,
    events: Iterable[L2SnapshotEvent | PublicTradeEvent],
    schema: pa.Schema,
) -> None:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in events:
        groups[event.utc_date].append(asdict(event))
    for day, rows in groups.items():
        directory = root / day / dataset
        directory.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(rows, schema=schema)
        identity = uuid4().hex
        final = directory / f"part-{identity}.parquet"
        temporary = directory / f".{identity}.tmp"
        try:
            pq.write_table(table, temporary)
            temporary.replace(final)
        finally:
            temporary.unlink(missing_ok=True)


def _read_parts(root: Path, dataset: str) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    for path in sorted(root.glob(f"*/{dataset}/part-*.parquet")):
        for row in pq.read_table(path).to_pylist():
            rows.append(_mapping(row))
    return tuple(rows)


def _l2_from_row(row: Mapping[str, object]) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        symbol=_text(row, "symbol"),
        exchange_ts_ms=_integer(row, "exchange_ts_ms"),
        received_ts_ns=_integer(row, "received_ts_ns"),
        bids=tuple(_level_from_row(item) for item in _list(row, "bids")),
        asks=tuple(_level_from_row(item) for item in _list(row, "asks")),
        source=_text(row, "source"),
    )


def _trade_from_row(row: Mapping[str, object]) -> PublicTradeEvent:
    side = _text(row, "aggressor_side")
    if side not in {"buy", "sell"}:
        raise ValueError("aggressor_side must be buy|sell")
    return PublicTradeEvent(
        symbol=_text(row, "symbol"),
        aggressor_side="buy" if side == "buy" else "sell",
        price=_number(row, "price"),
        size=_number(row, "size"),
        transaction_hash=_text(row, "transaction_hash"),
        exchange_ts_ms=_integer(row, "exchange_ts_ms"),
        received_ts_ns=_integer(row, "received_ts_ns"),
        trade_id=_integer(row, "trade_id"),
        buyer=_text(row, "buyer"),
        seller=_text(row, "seller"),
        source=_text(row, "source"),
    )


def _level_from_row(value: object) -> BookLevel:
    row = _mapping(value)
    return BookLevel(
        price=_number(row, "price"),
        size=_number(row, "size"),
        order_count=_integer(row, "order_count"),
    )


def _gap_from_row(row: Mapping[str, object]) -> StreamGap:
    return StreamGap(
        symbol=_text(row, "symbol"),
        channel=_text(row, "channel"),
        detected_ts_ns=_integer(row, "detected_ts_ns"),
        reason=_text(row, "reason"),
        previous_exchange_ts_ms=_optional_integer(row, "previous_exchange_ts_ms"),
        next_exchange_ts_ms=_optional_integer(row, "next_exchange_ts_ms"),
    )


def _json_object(payload: str) -> Mapping[str, object]:
    value: object = json.loads(payload)
    return _mapping(value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("archive row must be an object")
    return value


def _list(row: Mapping[str, object], key: str) -> list[object]:
    value = row.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_integer(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer or null")
    return value


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)
