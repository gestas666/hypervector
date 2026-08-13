"""Tests for recoverable taker-only repair of stored trade bundles."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    write_gzip_json,
    write_json,
)
from hypervector.data.oxa_trade_repair import repair_trade_bundle
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    load_trade_jsonl,
    trade_output_directory,
)


def test_trade_bundle_repair_is_dry_run_then_recoverable(tmp_path: Path) -> None:
    """Repair must preserve the inflated bundle before publishing takers only."""
    request = OxaTradeRequest(
        "BTC",
        datetime(2026, 7, 26, 23, 50, tzinfo=UTC),
        datetime(2026, 7, 26, 23, 51, tzinfo=UTC),
    )
    directory = _write_inflated_bundle(tmp_path, request)

    preview = repair_trade_bundle(directory)

    assert preview.previous_trade_count == 2
    assert preview.repaired_trade_count == 1
    assert preview.applied is False
    assert load_trade_jsonl(directory / "trades.jsonl.gz").shape[0] == 2

    repaired = repair_trade_bundle(directory, apply=True)

    assert repaired.applied is True
    assert repaired.backup_directory.is_dir()
    assert load_trade_jsonl(directory / "trades.jsonl.gz").shape[0] == 1
    backup = repaired.backup_directory
    assert load_trade_jsonl(backup / "trades.jsonl.gz").shape[0] == 2
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["normalization_version"] == TRADE_NORMALIZATION_VERSION
    assert manifest["trade_count"] == 1
    assert manifest["repair"]["previous_trade_count"] == 2


def _write_inflated_bundle(
    data_root: Path,
    request: OxaTradeRequest,
) -> Path:
    directory = trade_output_directory(data_root, request)
    raw = directory / "raw"
    raw.mkdir(parents=True)
    payload = _participant_payload()
    raw_path = raw / "page-0001.json.gz"
    write_gzip_json(raw_path, payload)
    trades_path = directory / "trades.jsonl.gz"
    with gzip_text_writer(trades_path) as handle:
        for trade_id, side in ((7, "sell"), (8, "sell")):
            row = {
                "aggressor_side": side,
                "price": "65370",
                "size": "0.00133",
                "source": "0xarchive_hyperliquid_public_trades",
                "symbol": "BTC",
                "trade_id": trade_id,
                "trade_id_source": "vendor",
                "ts_exchange_ms": 1_785_109_800_000,
                "vendor_request_id": "request-1",
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "complete": True,
        "continuation_cursor": None,
        "files": {
            "raw/page-0001.json.gz": file_evidence(raw_path),
            "trades.jsonl.gz": file_evidence(trades_path),
        },
        "max_pages": 1,
        "observed_end": "2026-07-26T23:50:00Z",
        "observed_start": "2026-07-26T23:50:00Z",
        "page_count": 1,
        "page_limit": 1000,
        "raw_fill_count": 2,
        "request_ids": ["request-1"],
        "requested_end": request.end.isoformat(),
        "requested_start": request.start.isoformat(),
        "schema_version": 1,
        "source": "0xarchive_hyperliquid_public_trades",
        "surrogate_trade_id_count": 0,
        "symbol": request.symbol,
        "trade_count": 2,
        "unresolved_fill_groups": 0,
        "venue": "hyperliquid",
    }
    write_json(directory / "manifest.json", manifest)
    return directory


def _participant_payload() -> dict[str, object]:
    return {
        "success": True,
        "data": [
            {
                "symbol": "BTC",
                "side": "B",
                "price": "65370",
                "size": "0.00133",
                "timestamp": "2026-07-26T23:50:00Z",
                "tx_hash": "0x0",
                "trade_id": 7,
                "order_id": 10,
                "crossed": False,
            },
            {
                "symbol": "BTC",
                "side": "A",
                "price": "65370",
                "size": "0.00133",
                "timestamp": "2026-07-26T23:50:00Z",
                "tx_hash": "0x0",
                "trade_id": 7,
                "order_id": 11,
                "crossed": True,
            },
        ],
        "meta": {"count": 2, "request_id": "request-1"},
    }
