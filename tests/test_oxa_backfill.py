"""Tests for resumable 0xArchive market-evidence backfill orchestration."""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
    _acquire_task,
    _execute_with_retry,
    _existing_result,
    _task_directory,
    iter_backfill_tasks,
    run_oxa_backfill,
    run_oxa_tasks,
)
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryError,
    output_directory,
)
from hypervector.data.oxa_prices import OxaPriceRequest, price_output_directory
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    trade_output_directory,
)


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


def test_optional_price_tasks_cover_same_windows(tmp_path: Path) -> None:
    """Mark/oracle evidence must use the identical resumable time partition."""
    base = _config(tmp_path)
    config = OxaBackfillConfig(
        base.symbol,
        base.start,
        base.end,
        base.data_root,
        include_prices=True,
    )

    tasks = tuple(iter_backfill_tasks(config))

    assert [(task.kind, task.start.hour, task.end.hour) for task in tasks] == [
        ("book", 0, 1),
        ("trade", 0, 1),
        ("price", 0, 1),
        ("book", 1, 2),
        ("trade", 1, 2),
        ("price", 1, 2),
    ]


def test_hip3_resume_can_skip_books_and_add_trade_and_price_families(
    tmp_path: Path,
) -> None:
    config = OxaBackfillConfig(
        "xyz:MU",
        datetime(2026, 2, 26, 17, tzinfo=UTC),
        datetime(2026, 2, 26, 18, tzinfo=UTC),
        tmp_path,
        include_prices=True,
        market_family="hip3",
    )

    tasks = tuple(iter_backfill_tasks(config))

    assert [task.kind for task in tasks] == ["book", "trade", "price"]
    assert _task_directory(config, tasks[1]).name
    assert _task_directory(config, tasks[2]).name


def test_price_only_mode_does_not_repeat_book_or_trade_requests(tmp_path: Path) -> None:
    """A price-context continuation must not redownload other data families."""
    base = _config(tmp_path)
    config = OxaBackfillConfig(
        base.symbol,
        base.start,
        base.end,
        base.data_root,
        chunk=timedelta(days=1),
        price_only=True,
    )

    tasks = tuple(iter_backfill_tasks(config))

    assert [(task.kind, task.start, task.end) for task in tasks] == [
        ("price", base.start, base.end)
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
        ({"price_max_pages": 0}, "price_max_pages"),
        ({"price_only": "yes"}, "price_only"),
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
        normalization = (
            {"normalization_version": TRADE_NORMALIZATION_VERSION}
            if count_key == "trade_count"
            else {}
        )
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
                    **normalization,
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


def test_resume_rejects_stale_trade_normalization(tmp_path: Path) -> None:
    """A pre-taker-only trade bundle must not be silently reused."""
    full = _config(tmp_path)
    config = OxaBackfillConfig(
        full.symbol,
        full.start,
        full.start + timedelta(hours=1),
        full.data_root,
    )
    request = OxaTradeRequest(
        config.symbol,
        config.start,
        config.end,
        1000,
        config.trade_max_pages,
        config.timeout_seconds,
    )
    directory = trade_output_directory(tmp_path, request)
    directory.mkdir(parents=True)
    evidence = directory / "evidence.bin"
    evidence.write_bytes(b"verified")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "complete": True,
                "source": "0xarchive_hyperliquid_public_trades",
                "symbol": config.symbol,
                "requested_start": config.start.isoformat(),
                "requested_end": config.end.isoformat(),
                "trade_count": 1,
                "page_count": 1,
                "files": {
                    "evidence.bin": {
                        "bytes": evidence.stat().st_size,
                        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="normalization is stale"):
        _existing_result(
            config,
            OxaBackfillTask("trade", config.start, config.end),
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


def test_default_retry_budget_survives_sustained_transient_vendor_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Long archive jobs should outlive a sub-minute vendor 5xx incident."""
    config = _config(tmp_path)
    task = OxaBackfillTask("book", config.start, config.start + timedelta(hours=1))
    expected = SimpleNamespace(task=task)
    calls = 0

    def acquire(*_args: object) -> object:
        nonlocal calls
        calls += 1
        if calls < 10:
            raise OxaHistoryError("temporary", status_code=500)
        return expected

    monkeypatch.setattr("hypervector.data.oxa_backfill._acquire_task", acquire)
    monkeypatch.setattr("hypervector.data.oxa_backfill.time.sleep", lambda _delay: None)

    result = _execute_with_retry(config, task, "test-key")

    assert result is expected
    assert calls == 10


def test_exhausted_retry_reports_exact_task_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final transport failure must identify the resumable task boundary."""
    config = _config(tmp_path)
    task = OxaBackfillTask("book", config.start, config.start + timedelta(hours=1))

    def fail(*_args: object) -> object:
        raise OxaHistoryError("temporary", status_code=503)

    monkeypatch.setattr("hypervector.data.oxa_backfill._acquire_task", fail)
    monkeypatch.setattr("hypervector.data.oxa_backfill.time.sleep", lambda _delay: None)

    with pytest.raises(OxaHistoryError, match="book backfill failed") as captured:
        _execute_with_retry(config, task, "test-key")

    assert task.start.isoformat() in str(captured.value)
    assert task.end.isoformat() in str(captured.value)
    assert captured.value.status_code == 503


@pytest.mark.parametrize("kind", ["book", "trade", "price"])
def test_acquire_task_publishes_only_complete_normalized_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """Every data family publishes only after bounded fetch completion."""
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
    elif kind == "trade":
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
    else:
        fetched = SimpleNamespace(complete=True, snapshots=(1, 2, 3, 4), pages=(1, 2))
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.OxaPriceClient", lambda **_kwargs: object()
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.fetch_price_history",
            lambda *_args: fetched,
        )
        monkeypatch.setattr(
            "hypervector.data.oxa_backfill.store_price_history",
            lambda *_args: stored,
        )

    result = _acquire_task(config, task, "test-key")

    assert result.directory == stored.directory
    assert result.skipped is False
    assert result.rows == {"book": 2, "trade": 3, "price": 4}[kind]


def test_price_task_directory_uses_price_request_contract(tmp_path: Path) -> None:
    """Resumption identity must resolve to the immutable price directory."""
    base = _config(tmp_path)
    config = OxaBackfillConfig(
        base.symbol,
        base.start,
        base.end,
        base.data_root,
        include_prices=True,
    )
    task = OxaBackfillTask("price", base.start, base.start + timedelta(hours=1))
    request = OxaPriceRequest(
        config.symbol,
        task.start,
        task.end,
        1000,
        config.price_max_pages,
        config.timeout_seconds,
    )

    assert _task_directory(config, task) == price_output_directory(tmp_path, request)


def test_explicit_task_runner_does_not_expand_targeted_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A signal-window job runs only its declared tasks."""
    config = _config(tmp_path, workers=1)
    tasks = (
        OxaBackfillTask("book", config.start, config.start + timedelta(minutes=1)),
        OxaBackfillTask(
            "book",
            config.start + timedelta(hours=1),
            config.start + timedelta(hours=1, minutes=1),
        ),
    )
    observed: list[OxaBackfillTask] = []

    def execute(
        _config: OxaBackfillConfig,
        task: OxaBackfillTask,
        _api_key: str,
    ) -> OxaBackfillResult:
        observed.append(task)
        return OxaBackfillResult(task, tmp_path / "bundle", False, 1, 1)

    monkeypatch.setattr("hypervector.data.oxa_backfill._execute_with_retry", execute)

    results = run_oxa_tasks(
        config,
        tasks=tasks,
        api_key="test-key",
        progress=lambda _: None,
    )

    assert tuple(observed) == tasks
    assert tuple(result.task for result in results) == tasks
