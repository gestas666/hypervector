"""Validated archive inputs for BTC liquidation covariate replay."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from hypervector.research.btc_liquidation_covariate_inputs import (
    archive_hour_pairs,
    load_book_rows,
    load_trade_rows,
    parse_book_snapshot,
    parse_public_trade,
)


def _levels(*, start: int, step: int, count: int = 20) -> list[dict[str, object]]:
    """Build vendor-shaped exact-string depth."""
    return [
        {"px": str(start + step * index), "sz": "1.25", "n": index + 1}
        for index in range(count)
    ]


def _book_row(timestamp_ms: int, *, count: int = 20) -> dict[str, object]:
    """Build one normalized 0xArchive book row."""
    bids = _levels(start=100, step=-1, count=count)
    asks = _levels(start=101, step=1, count=count)
    return {
        "source": "0xarchive_hyperliquid_native_l2",
        "symbol": "BTC",
        "ts_exchange_ms": timestamp_ms,
        "vendor_request_id": "request-book",
        "best_bid": "100",
        "best_ask": "101",
        "n_bids": count,
        "n_asks": count,
        "bids": bids,
        "asks": asks,
    }


def _trade_row(timestamp_ms: int, trade_id: int) -> dict[str, object]:
    """Build one normalized taker-only public trade row."""
    return {
        "source": "0xarchive_hyperliquid_public_trades",
        "symbol": "BTC",
        "ts_exchange_ms": timestamp_ms,
        "vendor_request_id": "request-trade",
        "trade_id": trade_id,
        "trade_id_source": "tid",
        "aggressor_side": "buy",
        "price": "100.5",
        "size": "2.25",
    }


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    """Write deterministic gzip JSONL fixture rows."""
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def test_parsers_preserve_exact_prices_sizes_and_trade_identity() -> None:
    """Convert vendor strings to exact-decimal validated replay models."""
    book = parse_book_snapshot(_book_row(1_000))
    trade = parse_public_trade(_trade_row(1_001, 77))

    assert book.complete is True
    assert str(book.bids[0].price) == "100"
    assert str(book.asks[0].size) == "1.25"
    assert trade.trade_id == 77
    assert str(trade.notional) == "226.125"


def test_book_parser_rejects_summary_depth_mismatch() -> None:
    """Fail rather than accepting a success-shaped best-price summary."""
    row = _book_row(1_000)
    row["best_ask"] = "102"

    with pytest.raises(ValueError, match="best prices"):
        parse_book_snapshot(row)


def test_window_loaders_use_half_open_bounds_and_reject_duplicate_trades(
    tmp_path: Path,
) -> None:
    """Load only the explicit interval and preserve unique public-trade IDs."""
    books = tmp_path / "books.jsonl.gz"
    trades = tmp_path / "trades.jsonl.gz"
    _write_rows(
        books, [_book_row(999), _book_row(1_000), _book_row(1_999), _book_row(2_000)]
    )
    _write_rows(
        trades,
        [
            _trade_row(999, 1),
            _trade_row(1_000, 2),
            _trade_row(1_999, 3),
            _trade_row(2_000, 4),
        ],
    )

    loaded_books = load_book_rows((books,), start_ms=1_000, end_ms=2_000)
    loaded_trades = load_trade_rows((trades,), start_ms=1_000, end_ms=2_000)

    assert tuple(row.ts_exchange_ms for row in loaded_books) == (1_000, 1_999)
    assert tuple(row.trade_id for row in loaded_trades) == (2, 3)

    duplicate = tmp_path / "duplicate.jsonl.gz"
    _write_rows(duplicate, [_trade_row(1_500, 2)])
    with pytest.raises(ValueError, match="duplicate trade identities"):
        load_trade_rows((trades, duplicate), start_ms=1_000, end_ms=2_000)


def test_window_loader_collapses_only_exact_cross_hour_trade_overlap(
    tmp_path: Path,
) -> None:
    """Inclusive vendor hour boundaries cannot double-count an identical trade."""
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"
    boundary = _trade_row(3_600_000, 77)
    repeated = dict(boundary)
    repeated["vendor_request_id"] = "request-next-hour"
    _write_rows(first, [boundary])
    _write_rows(second, [repeated])

    rows = load_trade_rows((first, second), start_ms=3_599_000, end_ms=3_601_000)

    assert len(rows) == 1
    assert rows[0].trade_id == 77


def test_archive_task_records_require_exact_book_trade_pairs(tmp_path: Path) -> None:
    """Bind each acquired UTC hour to exactly one verified book and trade file."""
    book_dir = tmp_path / "book"
    trade_dir = tmp_path / "trade"
    book_dir.mkdir()
    trade_dir.mkdir()
    _write_rows(book_dir / "books.jsonl.gz", [_book_row(1_000)])
    _write_rows(trade_dir / "trades.jsonl.gz", [_trade_row(1_000, 1)])
    base = {
        "start_utc": "1970-01-01T00:00:01+00:00",
        "end_utc": "1970-01-01T01:00:01+00:00",
    }
    records = (
        {
            **base,
            "kind": "book",
            "directory": str(book_dir),
            "files": {"books.jsonl.gz": {}},
        },
        {
            **base,
            "kind": "trade",
            "directory": str(trade_dir),
            "files": {"trades.jsonl.gz": {}},
        },
    )

    pairs = archive_hour_pairs(records)

    assert len(pairs) == 1
    assert pairs[0].start_ms == 1_000
    assert pairs[0].end_ms == 3_601_000
    assert pairs[0].book_path == book_dir / "books.jsonl.gz"
    assert pairs[0].trade_path == trade_dir / "trades.jsonl.gz"

    with pytest.raises(ValueError, match="paired"):
        archive_hour_pairs(records[:1])


def test_archive_pairs_follow_manifest_declared_uncompressed_book_file(
    tmp_path: Path,
) -> None:
    """Retain a verified legacy books.jsonl source instead of assuming gzip."""
    book_dir = tmp_path / "legacy-book"
    trade_dir = tmp_path / "trade"
    book_dir.mkdir()
    trade_dir.mkdir()
    book_path = book_dir / "books.jsonl"
    book_path.write_text(json.dumps(_book_row(1_000)) + "\n", encoding="utf-8")
    trade_path = trade_dir / "trades.jsonl.gz"
    _write_rows(trade_path, [_trade_row(1_000, 1)])
    base = {
        "start_utc": "1970-01-01T00:00:01+00:00",
        "end_utc": "1970-01-01T01:00:01+00:00",
    }
    records = (
        {
            **base,
            "kind": "book",
            "directory": str(book_dir),
            "files": {"books.jsonl": {}},
        },
        {
            **base,
            "kind": "trade",
            "directory": str(trade_dir),
            "files": {"trades.jsonl.gz": {}},
        },
    )

    pairs = archive_hour_pairs(records)

    assert pairs[0].book_path == book_path
    assert pairs[0].trade_path == trade_path
