"""Replay-compatible backend order-book archive tests."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.data.book_align import load_l2_jsonl
from hypervector.data.book_record import append_book_snapshot
from hypervector.paper.book import BookLevel, BookSnapshot


def test_append_existing_snapshot_writes_twenty_levels_and_reloads(tmp_path: Path) -> None:
    bids = tuple(BookLevel(100.0 - index, 1.0 + index) for index in range(25))
    asks = tuple(BookLevel(101.0 + index, 2.0 + index) for index in range(25))
    snapshot = BookSnapshot(
        symbol="BTC",
        bids=bids,
        asks=asks,
        ts_recv_ms=1_784_992_000_050.0,
        ts_exchange_ms=1_784_992_000_000.0,
        source="hl_rest_l2",
    )

    row = append_book_snapshot(tmp_path, snapshot, depth_levels=20, run_id="run-1")

    path = Path(str(row["_path"]))
    stored = json.loads(path.read_text(encoding="utf-8").strip())
    assert stored["run_id"] == "run-1"
    assert len(stored["bids"]) == 20
    assert len(stored["asks"]) == 20
    replay = load_l2_jsonl(path)
    assert len(replay) == 1
    assert replay.iloc[0]["best_bid"] == 100.0
    assert replay.iloc[0]["best_ask"] == 101.0

