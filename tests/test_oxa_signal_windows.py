"""Tests for targeted, causal 0xArchive HYPE signal-window acquisition."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_signal_windows import (
    OxaSignalWindow,
    audit_signal_windows,
    build_signal_windows,
    tasks_for_signal_windows,
)
from hypervector.data.oxa_storage import file_evidence


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "side": ["long", "short"],
            "signal_time_utc": [
                "2025-07-29T07:49:00+00:00",
                "2025-07-29T08:19:00+00:00",
            ],
            "entry_time_utc": [
                "2025-07-29T07:50:00+00:00",
                "2025-07-29T08:20:00+00:00",
            ],
        }
    )


def test_signal_windows_use_entry_availability_not_bar_open_time() -> None:
    """The causal minute ends at the next-minute entry decision boundary."""
    windows = build_signal_windows(_features(), pre_seconds=60, post_seconds=10)

    assert len(windows) == 2
    first = windows[0]
    assert first.signal_time == datetime(2025, 7, 29, 7, 49, tzinfo=UTC)
    assert first.entry_time == datetime(2025, 7, 29, 7, 50, tzinfo=UTC)
    assert first.start == datetime(2025, 7, 29, 7, 49, tzinfo=UTC)
    assert first.end == datetime(2025, 7, 29, 7, 50, 10, tzinfo=UTC)
    assert first.side == "long"


def test_signal_windows_reject_duplicate_or_noncausal_rows() -> None:
    """Ambiguous labels must fail before any credit-bearing request is made."""
    duplicate = pd.concat([_features(), _features().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate entry times"):
        build_signal_windows(duplicate, pre_seconds=60, post_seconds=10)

    noncausal = _features()
    noncausal.loc[0, "signal_time_utc"] = noncausal.loc[0, "entry_time_utc"]
    with pytest.raises(ValueError, match="before entry time"):
        build_signal_windows(noncausal, pre_seconds=60, post_seconds=10)


def test_signal_windows_create_book_only_tasks_with_exact_bounds() -> None:
    """The targeted job must not silently widen into trades or prices."""
    windows = build_signal_windows(_features(), pre_seconds=60, post_seconds=10)
    tasks = tasks_for_signal_windows(windows)

    assert [task.kind for task in tasks] == ["book", "book"]
    assert tasks[0].start == windows[0].start
    assert tasks[0].end == windows[0].end


def test_audit_requires_hashes_and_pre_and_post_entry_coverage(tmp_path: Path) -> None:
    """A vendor-complete bundle is insufficient without causal timing coverage."""
    window = build_signal_windows(_features().iloc[[0]], 60, 10)[0]
    _write_bundle(tmp_path, window, include_post=True)

    audit = audit_signal_windows(
        data_root=tmp_path,
        symbol="HYPE",
        depth=20,
        windows=(window,),
        maximum_pre_entry_age_ms=1_000,
        maximum_post_entry_delay_ms=1_000,
    )

    assert audit.complete is True
    assert audit.expected_signals == 1
    assert audit.causal_covered == 1
    assert audit.execution_covered == 1
    assert audit.total_rows == 2
    assert audit.rows[0].last_pre_entry_age_ms == 500
    assert audit.rows[0].first_post_entry_delay_ms == 300


def test_audit_reports_missing_execution_snapshot_without_success_shape(
    tmp_path: Path,
) -> None:
    """Missing post-entry depth remains an explicit incomplete acquisition."""
    window = build_signal_windows(_features().iloc[[0]], 60, 10)[0]
    _write_bundle(tmp_path, window, include_post=False)

    audit = audit_signal_windows(
        data_root=tmp_path,
        symbol="HYPE",
        depth=20,
        windows=(window,),
        maximum_pre_entry_age_ms=1_000,
        maximum_post_entry_delay_ms=1_000,
    )

    assert audit.complete is False
    assert audit.causal_covered == 1
    assert audit.execution_covered == 0
    assert audit.rows[0].status == "missing_post_entry_snapshot"


def _write_bundle(
    data_root: Path,
    window: OxaSignalWindow,
    *,
    include_post: bool,
) -> None:
    request = OxaBookRequest("HYPE", window.start, window.end, 20)
    directory = output_directory(data_root, request)
    directory.mkdir(parents=True)
    entry_ms = int(window.entry_time.timestamp() * 1_000)
    rows = [_book_row(entry_ms - 500)]
    if include_post:
        rows.append(_book_row(entry_ms + 300))
    books = directory / "books.jsonl.gz"
    with gzip.open(books, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    manifest = {
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_native_l2",
        "symbol": "HYPE",
        "requested_start": window.start.isoformat(),
        "requested_end": window.end.isoformat(),
        "requested_depth": 20,
        "complete": True,
        "continuation_cursor": None,
        "row_count": len(rows),
        "page_count": 1,
        "files": {"books.jsonl.gz": file_evidence(books)},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _book_row(timestamp_ms: int) -> dict[str, object]:
    return {
        "ts_exchange_ms": timestamp_ms,
        "symbol": "HYPE",
        "source": "0xarchive_hyperliquid_native_l2",
        "vendor_request_id": "test-request",
        "best_bid": "50.0",
        "best_ask": "50.1",
        "n_bids": 1,
        "n_asks": 1,
        "bids": [{"px": "50.0", "sz": "2.0", "n": 1}],
        "asks": [{"px": "50.1", "sz": "2.0", "n": 1}],
    }
