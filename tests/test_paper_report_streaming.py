"""Paper reporting must summarize ledgers without materializing their history."""

from __future__ import annotations

from pathlib import Path
import tracemalloc

from hypervector.paper.report import report_from_data_root, summarize_paper_decisions


def test_zero_recent_fills_returns_no_sample() -> None:
    """The --last 0 option must not accidentally return the full ledger."""
    rows = [{"action": "enter_long", "fill_model_id": "fixture"}]
    assert summarize_paper_decisions(rows, last_n=0)["last_market"] == []


def test_report_memory_is_independent_of_history_size(tmp_path: Path) -> None:
    """Counters and a bounded sample suffice for the public report contract."""
    ledger = tmp_path / "paper.jsonl"
    row = b'{"action":"enter_long","fill_model_id":"fixture","padding":"' + b'x' * 900 + b'"}\n'
    with ledger.open("wb") as stream:
        for _ in range(12000):
            stream.write(row)
    tracemalloc.start()
    try:
        report = report_from_data_root(tmp_path, decisions_path=ledger, last_n=2)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert report["rows"] == 12000
    assert report["market_fills"] == 12000
    assert len(report["last_market"]) == 2
    assert peak < 1_000_000
