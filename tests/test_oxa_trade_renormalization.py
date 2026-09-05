"""Tests for non-destructive current-version trade re-normalization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    verify_file_evidence,
    write_gzip_json,
)
from hypervector.data.oxa_trades import (
    TRADE_NORMALIZATION_VERSION,
    OxaTradeRequest,
    load_trade_jsonl,
    trade_output_directory,
)


def test_stale_trade_bundle_is_reproduced_into_separate_current_companion(
    tmp_path: Path,
) -> None:
    """Raw participant pages must be reused without overwriting old evidence."""
    from hypervector.data.oxa_trade_renormalization import renormalize_trade_task

    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    config = OxaBackfillConfig("BTC", start, end, tmp_path)
    task = OxaBackfillTask("trade", start, end)
    source = _stale_bundle(tmp_path, start, end)
    original_manifest = (source / "manifest.json").read_bytes()

    result = renormalize_trade_task(config, task)

    assert result.skipped is True
    assert result.rows == 1
    assert result.pages == 1
    assert result.directory != source
    assert result.directory.name.endswith("_trades_taker_only_v2")
    assert (source / "manifest.json").read_bytes() == original_manifest
    manifest = json.loads((result.directory / "manifest.json").read_text())
    assert manifest["normalization_version"] == TRADE_NORMALIZATION_VERSION
    assert (
        manifest["source_bundle"]["sha256"]
        == file_evidence(source / "manifest.json")["sha256"]
    )
    verify_file_evidence(result.directory, manifest["files"])
    frame = load_trade_jsonl(result.directory / "trades.jsonl.gz")
    assert len(frame) == 1
    assert frame.iloc[0]["aggressor_side"] == "sell"

    resumed = renormalize_trade_task(config, task)
    assert resumed == result


def test_mixed_task_runner_renormalizes_stale_trade_without_vendor_call(
    tmp_path: Path,
) -> None:
    """Only absent or already-current tasks should enter the vendor runner."""
    from hypervector.data.oxa_trade_renormalization import (
        run_oxa_tasks_with_trade_renormalization,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    config = OxaBackfillConfig("BTC", start, end, tmp_path)
    book = OxaBackfillTask("book", start, end)
    trade = OxaBackfillTask("trade", start, end)
    _stale_bundle(tmp_path, start, end)
    delegated: list[OxaBackfillTask] = []
    progressed: list[OxaBackfillResult] = []

    def standard_runner(
        selected: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: object,
    ) -> tuple[OxaBackfillResult, ...]:
        assert selected == config
        assert api_key == "configured-but-secret"
        delegated.extend(tasks)
        result = OxaBackfillResult(book, tmp_path / "book", False, 5, 1)
        progress(result)
        return (result,)

    results = run_oxa_tasks_with_trade_renormalization(
        config,
        tasks=(book, trade),
        api_key="configured-but-secret",
        progress=progressed.append,
        task_runner=standard_runner,
    )

    assert delegated == [book]
    assert [row.task for row in results] == [book, trade]
    assert len(progressed) == 2
    assert results[1].directory.name.endswith("_trades_taker_only_v2")


def _stale_bundle(root: Path, start: datetime, end: datetime) -> Path:
    request = OxaTradeRequest("BTC", start, end, max_pages=20)
    bundle = trade_output_directory(root, request)
    raw = bundle / "raw"
    raw.mkdir(parents=True)
    raw_path = raw / "page-0001.json.gz"
    write_gzip_json(raw_path, _participant_page(start))
    trades_path = bundle / "trades.jsonl.gz"
    with gzip_text_writer(trades_path) as handle:
        handle.write('{"legacy":"participant_rows"}\n')
    files = {
        "raw/page-0001.json.gz": file_evidence(raw_path),
        "trades.jsonl.gz": file_evidence(trades_path),
    }
    manifest = {
        "source": "0xarchive_hyperliquid_public_trades",
        "symbol": "BTC",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "max_pages": 20,
        "complete": True,
        "continuation_cursor": None,
        "trade_count": 2,
        "page_count": 1,
        "files": files,
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _participant_page(start: datetime) -> dict[str, object]:
    timestamp = start.isoformat().replace("+00:00", "Z")
    common: dict[str, object] = {
        "symbol": "BTC",
        "coin": "BTC",
        "price": "50000",
        "size": "0.01",
        "timestamp": timestamp,
        "tx_hash": "0xtest",
        "trade_id": 123,
    }
    return {
        "success": True,
        "data": [
            {**common, "side": "B", "order_id": 1, "crossed": False},
            {**common, "side": "A", "order_id": 2, "crossed": True},
        ],
        "meta": {"count": 2, "next_cursor": None, "request_id": "request-1"},
    }
