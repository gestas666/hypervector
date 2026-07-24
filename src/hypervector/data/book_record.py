"""Record HL public L2 book snapshots under data/cache/book/ (jsonl).

This is **storage only** — crown/trend strategies still trade on OHLCV.
Paper fills already poll live L2; this archive is for future book-feature
research and offline fill replay.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hypervector.data.hl import fetch_hl_l2_book
from hypervector.infra import ensure_data_layout


def _snapshot_to_row(snap: Any) -> dict[str, Any]:
    return {
        "ts_recv_ms": snap.ts_recv_ms,
        "ts_exchange_ms": snap.ts_exchange_ms,
        "symbol": snap.symbol,
        "source": snap.source,
        "best_bid": snap.best_bid(),
        "best_ask": snap.best_ask(),
        "n_bids": len(snap.bids),
        "n_asks": len(snap.asks),
        "bids": [{"px": lv.price, "sz": lv.size} for lv in snap.bids[:20]],
        "asks": [{"px": lv.price, "sz": lv.size} for lv in snap.asks[:20]],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def record_path(data_root: Path | str, symbol: str) -> Path:
    root = ensure_data_layout(data_root)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return root.cache_book / f"{symbol.upper()}_l2_{day}.jsonl"


def append_snapshot(data_root: Path | str, symbol: str = "BTC") -> dict[str, Any]:
    """Fetch one L2 snapshot and append to today's jsonl. Returns row dict."""
    snap = fetch_hl_l2_book(symbol)
    row = _snapshot_to_row(snap)
    path = record_path(data_root, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
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
