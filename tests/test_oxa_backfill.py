"""Tests for resumable paired 0xArchive backfill orchestration."""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillTask,
    _acquire_task,
    _execute_with_retry,
    _existing_result,
    iter_backfill_tasks,
    run_oxa_backfill,
)
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryError,
    output_directory,
)
from hypervector.data.oxa_trades import OxaTradeRequest, trade_output_directory


def _config(tmp_path: Path, *, workers: int = 4) -> OxaBackfillConfig:
    return OxaBackfillConfig(
        symbol="BTC",
        start=datetime(2026, 7, 26, 0, tzinfo=UTC),
        end=datetime(2026, 7, 26, 2, tzinfo=UTC),
        data_root=tmp_path,
        workers=workers,
    )


def test_tasks_cover_window_once_for_both_data_families(tmp_path: Path) -> None:
    """Hourly tasks must pair books and trades without temporal holes."""
    tasks = tuple(iter_backfill_tasks(_config(tmp_path)))

    assert [(task.kind, task.start.hour, task.end.hour) for task in tasks] == [
        ("book", 0, 1),
        ("trade", 0, 1),
        ("book", 1, 2),
        ("trade", 1, 2),
    ]


@pytest.mark.parametrize("workers", [0, 11])
def test_worker_count_cannot_exceed_account_concurrency(
    tmp_path: Path, workers: int
) -> None:
    """The orchestrator must remain within the documented Build envelope."""
    with pytest.raises(ValueError, match="workers"):
        _config(tmp_path, workers=workers)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"depth": 0}, "depth"),
        ({"timeout_seconds": 0.0}, "timeout"),
        ({"book_max_pages": 0}, "book_max_pages"),
        ({"trade_max_pages": 0}, "trade_max_pages"),
    ],
)
def test_config_fails_fast_on_invalid_request_bounds(
    tmp_path: Path,
    changes: dict[str, object],
    message: str,
) -> None:
    """Bad request dimensions must fail before worker threads are created."""
    values: dict[str, object] = {
        "symbol": "BTC",
        "start": datetime(2026, 7, 26, tzinfo=UTC),
        "end": datetime(2026, 7, 27, tzinfo=UTC),
        "data_root": tmp_path,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        OxaBackfillConfig(**values)  # type: ignore[arg-type]


def test_complete_existing_windows_resume_without_network(tmp_path: Path) -> None:
    """A resumed job skips complete paired bundles and reports their counts."""
    full = _config(tmp_path)
    config = OxaBackfillConfig(
        full.symbol,
        full.start,
        full.start + timedelta(hours=1),
        full.data_root,
    )
    book_request = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        config.book_max_pages,
        config.timeout_seconds,
    )
    trade_request = OxaTradeRequest(
        config.symbol,
        config.start,
        config.end,
        1000,
        config.trade_max_pages,
        config.timeout_seconds,
    )
    manifests = (
        (
            output_directory(tmp_path, book_request),
            "row_count",
            10,
            "0xarchive_hyperliquid_native_l2",
        ),
        (
            trade_output_directory(tmp_path, trade_request),
            "trade_count",
            7,
            "0xarchive_hyperliquid_public_trades",
        ),
    )
    for directory, count_key, count, source in manifests:
        directory.mkdir(parents=True)
        payload = directory / "evidence.bin"
        payload.write_bytes(b"verified")
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "complete": True,
                    "source": source,
                    "symbol": config.symbol,
                    "requested_start": config.start.isoformat(),
                    "requested_end": config.end.isoformat(),
                    count_key: count,
                    "page_count": 1,
                    "files": {
                        "evidence.bin": {
                            "bytes": payload.stat().st_size,
                            "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
    progress = []

    results = run_oxa_backfill(config, api_key="unused", progress=progress.append)

    assert len(results) == 2
    assert all(result.skipped for result in results)
    assert sum(result.rows for result in results) == 17
    assert len(progress) == 2


def test_resume_rejects_corrupted_completed_bundle(tmp_path: Path) -> None:
    """A complete manifest must not hide missing or modified evidence files."""
    full = _config(tmp_path)
    config = OxaBackfillConfig(
        full.symbol,
        full.start,
        full.start + timedelta(hours=1),
        full.data_root,
    )
    request = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        config.book_max_pages,
        config.timeout_seconds,
    )
    directory = output_directory(tmp_path, request)
    directory.mkdir(parents=True)
    (directory / "evidence.bin").write_bytes(b"corrupt")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "complete": True,
                "source": "0xarchive_hyperliquid_native_l2",
                "symbol": config.symbol,
                "requested_start": config.start.isoformat(),
                "requested_end": config.end.isoformat(),
                "row_count": 1,
                "page_count": 1,
                "files": {
                    "evidence.bin": {
                        "bytes": 7,
                        "sha256": "0" * 64,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum"):
        _existing_result(
            config,
            OxaBackfillTask("book", config.start, config.end),
        )


def test_retryable_transport_failure_retries_then_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transient transport failures retry without publishing success early."""
    config = _config(tmp_path)
    task = OxaBackfillTask("book", config.start, config.start + timedelta(hours=1))
    expected = SimpleNamespace(task=task)
    calls = 0

    def acquire(*_args: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OxaHistoryError("temporary", status_code=503)
        return expected

    monkeypatch.setattr("hypervector.data.oxa_backfill._acquire_task", acquire)
    monkeypatch.setattr("hypervector.data.oxa_backfill.time.sleep", lambda _delay: None)

    result = _execute_with_retry(config, task, "test-key")

    assert result is expected
    assert calls == 2


@pytest.mark.parametrize("kind", ["book", "trade"])
def test_acquire_task_publishes_only_complete_normalized_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """Both data families publish only after bounded fetch completion."""
    config = _config(tmp_path)
    task = OxaBackfillTask(  # type: ignore[arg-type]
        kind,
        config.start,
        config.start + timedelta(hours=1),
    )
    stored = SimpleNamespace(directory=tmp_path / kind)
    if kind == "book":
        fetched = SimpleNamespace(complete=True, snapshots=(1, 2), pages=(1,))
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.OxaHistoryClient", lambda **_kwargs: object()
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.fetch_orderbook_history",
            lambda *_args: fetched,
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.store_orderbook_history",
            lambda *_args: stored,
        )
    else:
        fetched = SimpleNamespace(
            complete=True,
            unresolved_fill_groups=0,
            trades=(1, 2, 3),
            pages=(1, 2),
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.OxaTradeClient", lambda **_kwargs: object()
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.fetch_trade_history",
            lambda *_args: fetched,
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.store_trade_history",
            lambda *_args: stored,
        )

    result = _acquire_task(config, task, "test-key")

    assert result.directory == stored.directory
    assert result.skipped is False
    assert result.rows == (2 if kind == "book" else 3)
