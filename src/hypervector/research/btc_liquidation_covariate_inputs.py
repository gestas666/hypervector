"""Validated 0xArchive inputs for BTC liquidation covariate replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path

from hypervector.data.oxa_api import parse_utc_timestamp_ms, positive_decimal
from hypervector.data.oxa_storage import open_text_reader
from hypervector.research.btc_liquidation_covariate_models import (
    BookSnapshot,
    PublicTrade,
    VisibleLevel,
)

_BOOK_SOURCE = "0xarchive_hyperliquid_native_l2"
_TRADE_SOURCE = "0xarchive_hyperliquid_public_trades"
_SYMBOL = "BTC"
_HOUR_MS = 60 * 60_000


@dataclass(frozen=True)
class ArchiveHour:
    """Exact paired normalized book/trade files for one acquired UTC hour."""

    start_ms: int
    end_ms: int
    book_path: Path
    trade_path: Path


def parse_book_snapshot(value: object) -> BookSnapshot:
    """Parse one normalized native-L2 row without float conversion."""
    row = _mapping(value, "book row")
    _require_source(row, _BOOK_SOURCE, "book")
    _text(row.get("vendor_request_id"), "book vendor request identity")
    bids = _parse_levels(row.get("bids"), "bids")
    asks = _parse_levels(row.get("asks"), "asks")
    if _integer(row.get("n_bids"), "n_bids") != len(bids) or _integer(
        row.get("n_asks"), "n_asks"
    ) != len(asks):
        raise ValueError("book depth counts do not reconcile")
    best_bid = positive_decimal(
        _text(row.get("best_bid"), "best_bid"), label="best_bid"
    )
    best_ask = positive_decimal(
        _text(row.get("best_ask"), "best_ask"), label="best_ask"
    )
    if best_bid != bids[0].price or best_ask != asks[0].price:
        raise ValueError("book best prices do not reconcile to depth")
    return BookSnapshot(
        _integer(row.get("ts_exchange_ms"), "book timestamp"), bids, asks
    )


def parse_public_trade(value: object) -> PublicTrade:
    """Parse one normalized taker-only public-trade row."""
    row = _mapping(value, "public trade row")
    _require_source(row, _TRADE_SOURCE, "public trade")
    _text(row.get("vendor_request_id"), "trade vendor request identity")
    _text(row.get("trade_id_source"), "trade identity source")
    side = row.get("aggressor_side")
    if side not in ("buy", "sell"):
        raise ValueError("trade aggressor_side must be buy or sell")
    return PublicTrade(
        ts_exchange_ms=_integer(row.get("ts_exchange_ms"), "trade timestamp"),
        trade_id=_integer(row.get("trade_id"), "trade identity"),
        aggressor_side=side,
        price=positive_decimal(_text(row.get("price"), "trade price"), label="price"),
        size=positive_decimal(_text(row.get("size"), "trade size"), label="size"),
    )


def load_book_rows(
    paths: tuple[Path, ...],
    *,
    start_ms: int,
    end_ms: int,
) -> tuple[BookSnapshot, ...]:
    """Load exact book rows inside one half-open replay window."""
    _validate_window(paths, start_ms, end_ms)
    rows = [
        parse_book_snapshot(value)
        for value in _json_rows(paths)
        if start_ms <= _row_timestamp(value) < end_ms
    ]
    return tuple(sorted(rows, key=lambda row: row.ts_exchange_ms))


def load_trade_rows(
    paths: tuple[Path, ...],
    *,
    start_ms: int,
    end_ms: int,
) -> tuple[PublicTrade, ...]:
    """Load unique public trades inside one half-open replay window."""
    _validate_window(paths, start_ms, end_ms)
    rows = [
        parse_public_trade(value)
        for value in _json_rows(paths)
        if start_ms <= _row_timestamp(value) < end_ms
    ]
    return _merge_unique_trades(rows)


def archive_hour_pairs(
    records: tuple[Mapping[str, object], ...],
) -> tuple[ArchiveHour, ...]:
    """Bind exact book and trade task evidence by acquired UTC hour."""
    grouped: dict[tuple[int, int], dict[str, Path]] = {}
    for record in records:
        start_ms, end_ms = _record_window(record)
        kind = _text(record.get("kind"), "archive task kind")
        if kind not in ("book", "trade"):
            raise ValueError("archive task kind must be book or trade")
        directory = Path(_text(record.get("directory"), "archive task directory"))
        key = (start_ms, end_ms)
        files = grouped.setdefault(key, {})
        if kind in files:
            raise ValueError("archive task evidence contains a duplicate pair member")
        files[kind] = _normalized_path(record, directory, kind)
    output: list[ArchiveHour] = []
    for (start_ms, end_ms), files in sorted(grouped.items()):
        if set(files) != {"book", "trade"}:
            raise ValueError("archive task evidence is not exactly paired")
        if any(not path.is_file() for path in files.values()):
            raise ValueError("paired archive normalized file is missing")
        output.append(ArchiveHour(start_ms, end_ms, files["book"], files["trade"]))
    return tuple(output)


def _merge_unique_trades(rows: list[PublicTrade]) -> tuple[PublicTrade, ...]:
    merged: dict[int, PublicTrade] = {}
    for row in sorted(rows, key=lambda item: (item.ts_exchange_ms, item.trade_id)):
        existing = merged.get(row.trade_id)
        if existing is not None and existing != row:
            raise ValueError("window contains conflicting duplicate trade identities")
        merged[row.trade_id] = row
    return tuple(
        sorted(merged.values(), key=lambda row: (row.ts_exchange_ms, row.trade_id))
    )


def _normalized_path(
    record: Mapping[str, object],
    directory: Path,
    kind: str,
) -> Path:
    files = _mapping(record.get("files"), "archive task files")
    candidates = (
        ("books.jsonl", "books.jsonl.gz")
        if kind == "book"
        else ("trades.jsonl", "trades.jsonl.gz")
    )
    matches = tuple(name for name in candidates if name in files)
    if len(matches) != 1:
        raise ValueError("archive task must declare exactly one normalized file")
    path = directory / matches[0]
    if not path.is_file():
        raise ValueError("paired archive normalized file is missing")
    return path


def _record_window(record: Mapping[str, object]) -> tuple[int, int]:
    start_ms = parse_utc_timestamp_ms(
        _text(record.get("start_utc"), "archive task start"), label="task start"
    )
    end_ms = parse_utc_timestamp_ms(
        _text(record.get("end_utc"), "archive task end"), label="task end"
    )
    if end_ms - start_ms != _HOUR_MS:
        raise ValueError("archive task window must equal one hour")
    return start_ms, end_ms


def _json_rows(paths: tuple[Path, ...]) -> list[object]:
    rows: list[object] = []
    for path in paths:
        with open_text_reader(path) as handle:
            rows.extend(json.loads(line) for line in handle)
    return rows


def _row_timestamp(value: object) -> int:
    return _integer(_mapping(value, "archive row").get("ts_exchange_ms"), "timestamp")


def _parse_levels(value: object, label: str) -> tuple[VisibleLevel, ...]:
    rows = _sequence(value, f"book {label}")
    levels: list[VisibleLevel] = []
    for value in rows:
        row = _mapping(value, f"book {label} level")
        _positive_integer(row.get("n"), f"book {label} order count")
        levels.append(
            VisibleLevel(
                positive_decimal(_text(row.get("px"), "level price"), label="price"),
                positive_decimal(_text(row.get("sz"), "level size"), label="size"),
            )
        )
    return tuple(levels)


def _require_source(row: Mapping[str, object], source: str, label: str) -> None:
    if row.get("source") != source or row.get("symbol") != _SYMBOL:
        raise ValueError(f"{label} source or symbol is inconsistent")


def _validate_window(paths: tuple[Path, ...], start_ms: int, end_ms: int) -> None:
    if not paths or any(not path.is_file() for path in paths):
        raise ValueError("replay input paths must be nonempty existing files")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("replay window must be positive and half-open")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    result = _integer(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result
