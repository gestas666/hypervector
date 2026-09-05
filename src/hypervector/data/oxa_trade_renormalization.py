"""Non-destructive current-version normalization of verified trade archives."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Protocol

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
    ProgressSink,
    run_oxa_tasks,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.data.oxa_trades import (
    TRADE_NORMALIZATION_VERSION,
    OxaTradeFetch,
    OxaTradePage,
    OxaTradeRequest,
    normalize_trade_pages,
    parse_trade_page,
    trade_output_directory,
    write_trade_jsonl,
)


@dataclass(frozen=True)
class _TradeSource:
    directory: Path
    manifest_path: Path
    manifest: Mapping[str, object]
    request: OxaTradeRequest
    raw_paths: tuple[Path, ...]
    normalized: OxaTradeFetch


class TaskRunner(Protocol):
    """Explicit vendor task-runner boundary used by mixed-source reuse."""

    def __call__(
        self,
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: ProgressSink,
    ) -> tuple[OxaBackfillResult, ...]: ...


def run_oxa_tasks_with_trade_renormalization(
    config: OxaBackfillConfig,
    *,
    tasks: tuple[OxaBackfillTask, ...],
    api_key: str,
    progress: ProgressSink,
    task_runner: TaskRunner = run_oxa_tasks,
) -> tuple[OxaBackfillResult, ...]:
    """Reuse stale raw trade pages and delegate only other explicit tasks."""
    stale, delegated = _partition_tasks(config, tasks)
    results: list[OxaBackfillResult] = []
    for task in stale:
        result = renormalize_trade_task(config, task)
        results.append(result)
        progress(result)
    if delegated:
        results.extend(
            task_runner(
                config,
                tasks=delegated,
                api_key=api_key,
                progress=progress,
            )
        )
    _validate_result_coverage(tasks, results)
    return tuple(sorted(results, key=lambda row: (row.task.start, row.task.kind)))


def renormalize_trade_task(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
) -> OxaBackfillResult:
    """Reproduce one stale trade bundle beside its immutable source."""
    if task.kind != "trade":
        raise ValueError("trade re-normalization requires a trade task")
    source = _load_source(config, task)
    output = renormalized_trade_output_directory(source.directory)
    if output.exists():
        _verify_output(output, source)
    else:
        _publish_output(output, source)
        _verify_output(output, source)
    return OxaBackfillResult(
        task,
        output,
        True,
        len(source.normalized.trades),
        len(source.normalized.pages),
    )


def renormalized_trade_output_directory(source: Path) -> Path:
    """Return the immutable current-normalization companion directory."""
    return source.with_name(f"{source.name}_{TRADE_NORMALIZATION_VERSION}")


def _partition_tasks(
    config: OxaBackfillConfig,
    tasks: tuple[OxaBackfillTask, ...],
) -> tuple[tuple[OxaBackfillTask, ...], tuple[OxaBackfillTask, ...]]:
    stale: list[OxaBackfillTask] = []
    delegated: list[OxaBackfillTask] = []
    for task in tasks:
        if task.kind == "trade" and _trade_source_is_stale(config, task):
            stale.append(task)
        else:
            delegated.append(task)
    return tuple(stale), tuple(delegated)


def _trade_source_is_stale(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
) -> bool:
    request = _request(config, task, config.trade_max_pages)
    manifest_path = trade_output_directory(config.data_root, request) / "manifest.json"
    if not manifest_path.is_file():
        return False
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"trade source manifest is malformed: {manifest_path}")
    return payload.get("normalization_version") != TRADE_NORMALIZATION_VERSION


def _validate_result_coverage(
    tasks: tuple[OxaBackfillTask, ...],
    results: list[OxaBackfillResult],
) -> None:
    expected = {(row.kind, row.start, row.end) for row in tasks}
    observed = [(row.task.kind, row.task.start, row.task.end) for row in results]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("mixed trade re-normalization results do not cover tasks")


def _load_source(config: OxaBackfillConfig, task: OxaBackfillTask) -> _TradeSource:
    initial = _request(config, task, config.trade_max_pages)
    directory = trade_output_directory(config.data_root, initial)
    manifest_path = directory / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"stale trade manifest is malformed: {manifest_path}")
    _validate_source_identity(config, task, payload)
    verify_file_evidence(directory, payload.get("files"))
    max_pages = _positive_integer(payload, "max_pages", config.trade_max_pages)
    request = _request(config, task, max_pages)
    raw_paths = _raw_paths(directory, payload)
    pages = tuple(_parse_raw_page(path, request) for path in raw_paths)
    normalized = normalize_trade_pages(pages)
    if not normalized.complete or normalized.unresolved_fill_groups:
        raise ValueError(
            f"stale trade source does not normalize completely: {directory}"
        )
    return _TradeSource(
        directory, manifest_path, payload, request, raw_paths, normalized
    )


def _validate_source_identity(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    payload: Mapping[str, object],
) -> None:
    valid = (
        payload.get("source") == "0xarchive_hyperliquid_public_trades"
        and payload.get("symbol") == config.symbol
        and payload.get("requested_start") == task.start.isoformat()
        and payload.get("requested_end") == task.end.isoformat()
        and payload.get("complete") is True
        and payload.get("continuation_cursor") is None
    )
    if not valid:
        raise ValueError("stale trade source identity or completeness mismatch")


def _raw_paths(directory: Path, manifest: Mapping[str, object]) -> tuple[Path, ...]:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("stale trade source files are missing")
    relative = sorted(
        key
        for key in files
        if isinstance(key, str)
        and key.startswith("raw/page-")
        and key.endswith(".json.gz")
    )
    page_count = _positive_integer(manifest, "page_count")
    if len(relative) != page_count:
        raise ValueError("stale trade raw-page count differs from manifest")
    expected = [f"raw/page-{index:04d}.json.gz" for index in range(1, page_count + 1)]
    if relative != expected:
        raise ValueError("stale trade raw pages are not contiguous")
    return tuple(directory / name for name in relative)


def _parse_raw_page(path: Path, request: OxaTradeRequest) -> OxaTradePage:
    with open_text_reader(path) as handle:
        payload = json.load(handle)
    return parse_trade_page(payload, request)


def _request(
    config: OxaBackfillConfig,
    task: OxaBackfillTask,
    max_pages: int,
) -> OxaTradeRequest:
    return OxaTradeRequest(
        config.symbol,
        task.start,
        task.end,
        1000,
        max_pages,
        config.timeout_seconds,
        market_family=config.market_family,
    )


def _publish_output(output: Path, source: _TradeSource) -> None:
    def writer(staging: Path) -> None:
        raw_directory = staging / "raw"
        raw_directory.mkdir()
        files = _link_raw_pages(raw_directory, source.raw_paths)
        trades_path = staging / "trades.jsonl.gz"
        write_trade_jsonl(trades_path, source.normalized.trades)
        files[trades_path.name] = file_evidence(trades_path)
        write_json(staging / "manifest.json", _manifest(source, files))

    publish_immutable_directory(output, writer)


def _link_raw_pages(
    output: Path,
    source_paths: tuple[Path, ...],
) -> dict[str, dict[str, object]]:
    evidence: dict[str, dict[str, object]] = {}
    for source in source_paths:
        destination = output / source.name
        os.link(source, destination)
        evidence[f"raw/{source.name}"] = file_evidence(destination)
    return evidence


def _manifest(
    source: _TradeSource,
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    normalized = source.normalized
    first = normalized.trades[0].timestamp if normalized.trades else None
    last = normalized.trades[-1].timestamp if normalized.trades else None
    return {
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_public_trades",
        "venue": "hyperliquid",
        "market_family": source.request.market_family,
        "symbol": source.request.symbol,
        "requested_start": source.request.start.isoformat(),
        "requested_end": source.request.end.isoformat(),
        "page_limit": source.request.limit,
        "max_pages": source.request.max_pages,
        "request_ids": list(normalized.request_ids),
        "page_count": len(normalized.pages),
        "raw_fill_count": sum(len(page.fills) for page in normalized.pages),
        "trade_count": len(normalized.trades),
        "normalization_version": TRADE_NORMALIZATION_VERSION,
        "surrogate_trade_id_count": sum(
            trade.trade_id_source != "vendor" for trade in normalized.trades
        ),
        "unresolved_fill_groups": normalized.unresolved_fill_groups,
        "observed_start": first,
        "observed_end": last,
        "complete": normalized.complete,
        "continuation_cursor": normalized.continuation_cursor,
        "source_bundle": {
            "path": str(source.manifest_path.resolve()),
            **file_evidence(source.manifest_path),
        },
        "files": files,
    }


def _verify_output(output: Path, source: _TradeSource) -> None:
    manifest_path = output / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"re-normalized trade manifest is malformed: {manifest_path}")
    files = payload.get("files")
    expected = _manifest(source, files if isinstance(files, dict) else {})
    if payload != expected:
        raise ValueError(f"re-normalized trade manifest does not reproduce: {output}")
    verify_file_evidence(output, payload.get("files"))
    observed = _load_rows(output / "trades.jsonl.gz")
    expected_rows = tuple(trade.to_replay_row() for trade in source.normalized.trades)
    if observed != expected_rows:
        raise ValueError(f"re-normalized trade rows do not reproduce: {output}")


def _load_rows(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    with open_text_reader(path) as handle:
        for line in handle:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"re-normalized trade row is malformed: {path}")
            rows.append(row)
    return tuple(rows)


def _positive_integer(
    payload: Mapping[str, object],
    key: str,
    default: int | None = None,
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"stale trade {key} must be a positive integer")
    return value
