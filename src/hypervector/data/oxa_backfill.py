"""Resumable paired 0xArchive L2 and public-trade backfills."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from hypervector.data.oxa_api import OxaHistoryError, validate_symbol, validate_window
from hypervector.data.oxa_history import (
    OxaBookRequest,
    OxaHistoryClient,
    fetch_orderbook_history,
    output_directory,
    store_orderbook_history,
)
from hypervector.data.oxa_trades import (
    OxaTradeClient,
    OxaTradeRequest,
    fetch_trade_history,
    store_trade_history,
    trade_output_directory,
)
from hypervector.data.oxa_storage import verify_file_evidence

DataKind = Literal["book", "trade"]


@dataclass(frozen=True)
class OxaBackfillConfig:
    """Explicit scope and resource bounds for one paired history job."""

    symbol: str
    start: datetime
    end: datetime
    data_root: Path
    chunk: timedelta = timedelta(hours=1)
    depth: int = 20
    workers: int = 4
    retries: int = 3
    timeout_seconds: float = 30.0
    book_max_pages: int = 20
    trade_max_pages: int = 500

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("chunk must be positive")
        if not 1 <= self.workers <= 10:
            raise ValueError("workers must be between 1 and 10")
        if self.retries < 1:
            raise ValueError("retries must be at least 1")
        if not 1 <= self.depth <= 20:
            raise ValueError("depth must be between 1 and 20")
        if self.timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")
        if self.book_max_pages < 1:
            raise ValueError("book_max_pages must be at least 1")
        if self.trade_max_pages < 1:
            raise ValueError("trade_max_pages must be at least 1")


@dataclass(frozen=True)
class OxaBackfillTask:
    """One independently retryable data-family window."""

    kind: DataKind
    start: datetime
    end: datetime


@dataclass(frozen=True)
class OxaBackfillResult:
    """One completed or previously completed backfill task."""

    task: OxaBackfillTask
    directory: Path
    skipped: bool
    rows: int
    pages: int


ProgressSink = Callable[[OxaBackfillResult], None]


def iter_backfill_tasks(config: OxaBackfillConfig) -> Iterator[OxaBackfillTask]:
    """Yield paired hourly tasks covering the configured half-open window."""
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        yield OxaBackfillTask("book", start, end)
        yield OxaBackfillTask("trade", start, end)
        start = end


def run_oxa_backfill(
    config: OxaBackfillConfig,
    *,
    api_key: str,
    progress: ProgressSink,
) -> tuple[OxaBackfillResult, ...]:
    """Run a bounded worker pool and fail if any required window is incomplete."""
    tasks = tuple(iter_backfill_tasks(config))
    results: list[OxaBackfillResult] = []
    executor = ThreadPoolExecutor(max_workers=config.workers)
    try:
        futures = {
            executor.submit(_execute_with_retry, config, task, api_key): task
            for task in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            progress(result)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return tuple(sorted(results, key=lambda item: (item.task.start, item.task.kind)))


def _execute_with_retry(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    api_key: str,
) -> OxaBackfillResult:
    existing = _existing_result(config, task)
    if existing is not None:
        return existing
    for attempt in range(1, config.retries + 1):
        try:
            return _acquire_task(config, task, api_key)
        except OxaHistoryError as exc:
            if attempt == config.retries or not _retryable(exc):
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError("unreachable retry state")


def _existing_result(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
) -> OxaBackfillResult | None:
    directory = _task_directory(config, task)
    if not directory.exists():
        return None
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"existing backfill directory has no manifest: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("complete") is not True:
        raise ValueError(f"existing backfill window is incomplete: {directory}")
    expected_source = (
        "0xarchive_hyperliquid_native_l2"
        if task.kind == "book"
        else "0xarchive_hyperliquid_public_trades"
    )
    identity = (
        manifest.get("source") == expected_source
        and manifest.get("symbol") == config.symbol
        and manifest.get("requested_start") == task.start.isoformat()
        and manifest.get("requested_end") == task.end.isoformat()
    )
    if not identity:
        raise ValueError(f"existing backfill manifest identity mismatch: {directory}")
    rows_key = "row_count" if task.kind == "book" else "trade_count"
    rows = manifest.get(rows_key)
    pages = manifest.get("page_count")
    if not isinstance(rows, int) or not isinstance(pages, int):
        raise ValueError(f"existing backfill manifest has invalid counts: {directory}")
    verify_file_evidence(directory, manifest.get("files"))
    return OxaBackfillResult(task, directory, True, rows, pages)


def _acquire_task(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    api_key: str,
) -> OxaBackfillResult:
    if task.kind == "book":
        request = _book_request(config, task)
        fetched = fetch_orderbook_history(OxaHistoryClient(api_key=api_key), request)
        if not fetched.complete:
            raise ValueError(f"book max-pages exhausted for {task.start.isoformat()}")
        stored = store_orderbook_history(config.data_root, request, fetched)
        return OxaBackfillResult(
            task, stored.directory, False, len(fetched.snapshots), len(fetched.pages)
        )
    request = _trade_request(config, task)
    fetched = fetch_trade_history(OxaTradeClient(api_key=api_key), request)
    if not fetched.complete:
        raise ValueError(f"trade max-pages exhausted for {task.start.isoformat()}")
    if fetched.unresolved_fill_groups:
        raise ValueError(
            f"trade participant groups unresolved for {task.start.isoformat()}"
        )
    stored = store_trade_history(config.data_root, request, fetched)
    return OxaBackfillResult(
        task, stored.directory, False, len(fetched.trades), len(fetched.pages)
    )


def _book_request(config: OxaBackfillConfig, task: OxaBackfillTask) -> OxaBookRequest:
    return OxaBookRequest(
        config.symbol,
        task.start,
        task.end,
        config.depth,
        1000,
        config.book_max_pages,
        config.timeout_seconds,
    )


def _trade_request(config: OxaBackfillConfig, task: OxaBackfillTask) -> OxaTradeRequest:
    return OxaTradeRequest(
        config.symbol,
        task.start,
        task.end,
        1000,
        config.trade_max_pages,
        config.timeout_seconds,
    )


def _task_directory(config: OxaBackfillConfig, task: OxaBackfillTask) -> Path:
    if task.kind == "book":
        return output_directory(config.data_root, _book_request(config, task))
    return trade_output_directory(config.data_root, _trade_request(config, task))


def _retryable(exc: OxaHistoryError) -> bool:
    return exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500
