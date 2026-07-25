"""Record HL public L2 book snapshots under data/cache/book/ (jsonl).

This is **storage only** — crown/trend strategies still trade on OHLCV.
Paper fills already poll live L2; this archive is for future book-feature
research and offline fill replay.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

from hypervector.data.hl import fetch_hl_l2_book
from hypervector.infra import ensure_data_layout


class BookLevelLike(Protocol):
    """Structural type for one order-book level."""

    price: float
    size: float


class BookSnapshotLike(Protocol):
    """Structural type accepted by the storage-only archive."""

    ts_recv_ms: float
    ts_exchange_ms: float | None
    symbol: str
    source: str
    bids: Sequence[BookLevelLike]
    asks: Sequence[BookLevelLike]

    def best_bid(self) -> float | None: ...

    def best_ask(self) -> float | None: ...


def snapshot_to_row(
    snap: BookSnapshotLike,
    *,
    depth_levels: int = 20,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Serialize a fetched book snapshot for replay-compatible JSONL storage."""
    if depth_levels <= 0:
        raise ValueError("depth_levels must be positive")
    return {
        "ts_recv_ms": snap.ts_recv_ms,
        "ts_exchange_ms": snap.ts_exchange_ms,
        "symbol": snap.symbol,
        "source": snap.source,
        "best_bid": snap.best_bid(),
        "best_ask": snap.best_ask(),
        "n_bids": len(snap.bids),
        "n_asks": len(snap.asks),
        "bids": [
            {"px": level.price, "sz": level.size}
            for level in snap.bids[:depth_levels]
        ],
        "asks": [
            {"px": level.price, "sz": level.size}
            for level in snap.asks[:depth_levels]
        ],
        "run_id": run_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def record_path(data_root: Path | str, symbol: str) -> Path:
    root = ensure_data_layout(data_root)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return root.cache_book / f"{symbol.upper()}_l2_{day}.jsonl"


def append_snapshot(data_root: Path | str, symbol: str = "BTC") -> dict[str, Any]:
    """Fetch one L2 snapshot and append to today's jsonl. Returns row dict."""
    snap = fetch_hl_l2_book(symbol)
    return append_book_snapshot(data_root, snap)


def append_book_snapshot(
    data_root: Path | str,
    snapshot: BookSnapshotLike,
    *,
    depth_levels: int = 20,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Append an already-fetched snapshot without another venue request."""
    row = snapshot_to_row(
        snapshot,
        depth_levels=depth_levels,
        run_id=run_id,
    )
    path = record_path(data_root, snapshot.symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    row["_path"] = str(path)
    return row


def run_book_recorder(
    data_root: Path | str,
    *,
    symbol: str = "BTC",
    interval_secs: float = 2.0,
    max_snapshots: int | None = None,
    stop_file: Path | str | None = None,
) -> dict[str, Any]:
    """Poll L2 until max_snapshots or stop_file appears."""
    n = 0
    last_path: str | None = None
    stop = Path(stop_file) if stop_file else None
    while True:
        if stop is not None and stop.exists():
            break
        if max_snapshots is not None and n >= int(max_snapshots):
            break
        row = append_snapshot(data_root, symbol)
        last_path = row.get("_path")
        n += 1
        time.sleep(max(0.2, float(interval_secs)))
    return {
        "ok": True,
        "snapshots": n,
        "symbol": symbol.upper(),
        "path": last_path,
        "stop_reason": "stop_file"
        if stop is not None and stop.exists()
        else ("max_snapshots" if max_snapshots is not None else "unknown"),
    }
