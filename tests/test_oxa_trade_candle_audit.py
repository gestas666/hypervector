"""Tests for point-in-time trade-tape versus venue-candle parity auditing."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.data.oxa_archive_audit import OxaArchiveAuditConfig
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_storage import file_evidence, gzip_text_writer, write_json
from hypervector.data.oxa_trade_candle_audit import (
    audit_trade_candle_parity,
    reconstruct_trade_candle_continuity,
    store_reconstructed_trade_candles,
)
from hypervector.data.oxa_trades import (
    OxaTradeRequest,
    TRADE_NORMALIZATION_VERSION,
    trade_output_directory,
)
from hypervector.research.hypertrader_source_adapter import (
    load_hyperliquid_candles,
    resample_hyperliquid_5m,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "oxa_trade_candle_audit.py"
RECONSTRUCT_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "oxa_trade_candle_reconstruct.py"
)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("oxa_trade_candle_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_reconstruct_script() -> ModuleType:
    spec = spec_from_file_location("oxa_trade_candle_reconstruct", RECONSTRUCT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_trade_candle_audit_marks_only_incomplete_execution_minutes(
    tmp_path: Path,
) -> None:
    """Volume/count disagreements must become explicit degraded minutes."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame(
        [
            _candle(start, 100.0, 1.0, 1),
            _candle(start + timedelta(minutes=1), 101.0, 2.0, 2),
        ]
    ).to_parquet(candles, index=False)

    report = audit_trade_candle_parity(config, candles)

    assert report.candle_minutes == 2
    assert report.trade_minutes == 2
    assert report.exact_bar_minutes == 1
    assert report.execution_complete_minutes == 1
    assert report.degraded_execution_minutes_utc == ("2025-03-01T00:01:00+00:00",)
    assert report.ordering_only_minutes_utc == ()
    assert report.max_trade_count_delta == 1
    assert report.candle_path == str(candles.resolve())
    assert report.to_dict()["execution_complete_ratio"] == 0.5


def test_trade_candle_audit_fingerprint_binds_empty_trade_manifest(
    tmp_path: Path,
) -> None:
    """An empty hour's manifest must remain bound into parity provenance."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    _write_archive(config, trade_rows=[])
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 0.0, 0)]).to_parquet(candles, index=False)
    before = audit_trade_candle_parity(config, candles)
    request = OxaTradeRequest("SOL", config.start, config.end, 1000, 500, 30.0)
    manifest_path = trade_output_directory(tmp_path, request) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw_fill_count"] = 1
    write_json(manifest_path, manifest)

    after = audit_trade_candle_parity(config, candles)

    assert before.trade_manifest_fingerprint != after.trade_manifest_fingerprint


def test_reconstruction_uses_trades_then_verified_no_trade_carry(
    tmp_path: Path,
) -> None:
    """Only archive-proven trade and no-trade minutes may repair candle gaps."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame(
        [
            _candle(start, 100.0, 1.0, 1),
            _candle(start + timedelta(minutes=2), 101.0, 0.0, 0),
        ]
    ).to_parquet(candles, index=False)

    reconstructed, report = reconstruct_trade_candle_continuity(config, candles)

    assert len(reconstructed) == 60
    assert reconstructed["timestamp"].is_unique
    assert reconstructed.iloc[1]["source"] == "hl_trade_reconstruction"
    assert reconstructed.iloc[1]["close"] == 101.0
    assert reconstructed.iloc[1]["volume"] == 1.0
    assert reconstructed.iloc[3]["source"] == "hl_verified_no_trade"
    assert reconstructed.iloc[3]["close"] == 101.0
    assert reconstructed.iloc[3]["volume"] == 0.0
    assert report.native_minutes == 2
    assert report.trade_reconstructed_minutes == 1
    assert report.verified_no_trade_minutes == 57


def test_reconstruction_merges_partition_boundary_minute(tmp_path: Path) -> None:
    """Disjoint prints split across hourly bundles must form one minute bar."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    boundary = start + timedelta(hours=1)
    left = OxaArchiveAuditConfig("SOL", start, boundary, tmp_path)
    right = OxaArchiveAuditConfig(
        "SOL",
        boundary,
        boundary + timedelta(hours=1),
        tmp_path,
    )
    combined = OxaArchiveAuditConfig(
        "SOL",
        start,
        boundary + timedelta(hours=1),
        tmp_path,
    )
    _write_archive(
        left,
        [
            _trade(start + timedelta(minutes=1)) | {"trade_id": 501},
            _trade(boundary) | {"trade_id": 502},
        ],
    )
    _write_archive(
        right,
        [_trade(boundary + timedelta(seconds=1)) | {"trade_id": 503}],
    )
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 0.0, 0)]).to_parquet(
        candles,
        index=False,
    )

    reconstructed, _ = reconstruct_trade_candle_continuity(combined, candles)

    boundary_bar = reconstructed.loc[reconstructed["timestamp"].eq(boundary)].iloc[0]
    assert boundary_bar["source"] == "hl_trade_reconstruction"
    assert boundary_bar["volume"] == 2.0
    assert boundary_bar["trade_count"] == 2


def test_reconstruction_rejects_trade_price_extrema_mismatch(tmp_path: Path) -> None:
    """A changed completed-5m high or low invalidates source-label repair."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    trades = [_trade(start + timedelta(minutes=index)) for index in range(5)]
    _write_archive(config, trades)
    candles = tmp_path / "candles.parquet"
    rows = [
        _candle(
            start + timedelta(minutes=index),
            100.0 if index == 0 else 101.0,
            1.0,
            1,
        )
        for index in range(5)
    ]
    rows[0]["high"] = 102.0
    pd.DataFrame(rows).to_parquet(candles, index=False)

    with pytest.raises(ValueError, match="5m price-extrema mismatch"):
        reconstruct_trade_candle_continuity(config, candles)


def test_reconstruction_reports_minute_extrema_difference_absorbed_at_5m(
    tmp_path: Path,
) -> None:
    """A 1m tape omission may remain usable when completed-5m OHLC is unchanged."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    trades = [_trade(start + timedelta(minutes=index)) for index in range(5)]
    trades[2] = trades[2] | {"price": "99"}
    _write_archive(config, trades)
    candles = tmp_path / "candles.parquet"
    rows = [
        _candle(
            start + timedelta(minutes=index),
            99.0 if index == 2 else (100.0 if index == 0 else 101.0),
            1.0,
            1,
        )
        for index in range(5)
    ]
    rows[0]["low"] = 99.0
    pd.DataFrame(rows).to_parquet(candles, index=False)

    _, report = reconstruct_trade_candle_continuity(config, candles)

    assert report.minute_price_extrema_difference_minutes == 1
    assert report.complete_five_minute_overlap_bars == 1
    assert report.five_minute_price_extrema_difference_bars == 0


def test_reconstruction_reports_volume_undercoverage_without_replacing_native(
    tmp_path: Path,
) -> None:
    """Native volume stays authoritative while tape undercoverage is measured."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 2.0, 2)]).to_parquet(candles, index=False)

    reconstructed, report = reconstruct_trade_candle_continuity(config, candles)

    assert reconstructed.iloc[0]["volume"] == 2.0
    assert report.execution_undercoverage_minutes == 1
    assert report.maximum_volume_undercoverage == 1.0
    assert report.maximum_trade_count_undercoverage == 1


def test_reconstruction_ignores_sub_tolerance_volume_roundoff(tmp_path: Path) -> None:
    """Floating-point summation noise must not become reported undercoverage."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    first = _trade(start) | {"size": "0.1", "trade_id": 100}
    second = _trade(start + timedelta(seconds=1)) | {
        "size": "0.7",
        "trade_id": 101,
    }
    _write_archive(config, [first, second])
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 0.8, 2)]).to_parquet(candles, index=False)

    _, report = reconstruct_trade_candle_continuity(config, candles)

    assert report.execution_undercoverage_minutes == 0
    assert report.maximum_volume_undercoverage == 0.0


def test_reconstruction_bundle_is_immutable_and_source_bound(tmp_path: Path) -> None:
    """Published continuity bars must retain exact candle and trade provenance."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    config = OxaArchiveAuditConfig("SOL", start, start + timedelta(hours=1), tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 1.0, 1)]).to_parquet(candles, index=False)
    output = tmp_path / "reconstructed"

    stored, report = store_reconstructed_trade_candles(config, candles, output)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert stored == output / "candles.parquet"
    assert report.trade_reconstructed_minutes == 1
    assert manifest["input_candle"] == file_evidence(candles)
    assert manifest["trade_manifest_fingerprint"] == report.trade_manifest_fingerprint
    assert manifest["files"]["candles.parquet"] == file_evidence(stored)
    loaded = load_hyperliquid_candles([stored])
    assert len(resample_hyperliquid_5m(loaded)) == 12
    with pytest.raises(FileExistsError, match="already exists"):
        store_reconstructed_trade_candles(config, candles, output)


def test_trade_candle_audit_script_writes_once(tmp_path: Path) -> None:
    """Parity evidence must be written immutably from explicit bounds."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    config = OxaArchiveAuditConfig("SOL", start, end, tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 1.0, 1)]).to_parquet(candles, index=False)
    output = tmp_path / "parity.json"
    arguments = [
        "--symbol",
        "SOL",
        "--start",
        start.isoformat(),
        "--end",
        end.isoformat(),
        "--data-root",
        str(tmp_path),
        "--candles",
        str(candles),
        "--out",
        str(output),
    ]
    module = _load_script()

    assert module.main(arguments) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["candle_path"] == str(
        candles.resolve()
    )
    assert module.main(arguments) == 1


def test_trade_candle_reconstruction_script_writes_once(tmp_path: Path) -> None:
    """The CLI must publish one immutable reconstruction bundle."""
    start = datetime(2025, 3, 1, tzinfo=UTC)
    end = start + timedelta(hours=1)
    config = OxaArchiveAuditConfig("SOL", start, end, tmp_path)
    _write_archive(config)
    candles = tmp_path / "candles.parquet"
    pd.DataFrame([_candle(start, 100.0, 1.0, 1)]).to_parquet(candles, index=False)
    output = tmp_path / "reconstructed"
    arguments = [
        "--symbol",
        "SOL",
        "--start",
        start.isoformat(),
        "--end",
        end.isoformat(),
        "--data-root",
        str(tmp_path),
        "--candles",
        str(candles),
        "--out",
        str(output),
    ]
    module = _load_reconstruct_script()

    assert module.main(arguments) == 0
    assert (output / "candles.parquet").is_file()
    assert module.main(arguments) == 1


def _write_archive(
    config: OxaArchiveAuditConfig,
    trade_rows: list[dict[str, object]] | None = None,
) -> None:
    book_request = OxaBookRequest(
        config.symbol,
        config.start,
        config.end,
        config.depth,
        1000,
        20,
        30.0,
    )
    trade_request = OxaTradeRequest(
        config.symbol, config.start, config.end, 1000, 500, 30.0
    )
    book_dir = output_directory(config.data_root, book_request)
    trade_dir = trade_output_directory(config.data_root, trade_request)
    book_dir.mkdir(parents=True)
    trade_dir.mkdir(parents=True)
    books = book_dir / "books.jsonl.gz"
    trades = trade_dir / "trades.jsonl.gz"
    _write_rows(books, [])
    if trade_rows is None:
        trade_rows = [_trade(config.start), _trade(config.start + timedelta(minutes=1))]
    _write_rows(trades, trade_rows)
    identity = {
        "complete": True,
        "symbol": config.symbol,
        "requested_start": config.start.isoformat(),
        "requested_end": config.end.isoformat(),
    }
    write_json(
        book_dir / "manifest.json",
        identity
        | {
            "source": "0xarchive_hyperliquid_native_l2",
            "row_count": 0,
            "coalesced_same_ms": 0,
            "files": {books.name: file_evidence(books)},
        },
    )
    write_json(
        trade_dir / "manifest.json",
        identity
        | {
            "source": "0xarchive_hyperliquid_public_trades",
            "normalization_version": TRADE_NORMALIZATION_VERSION,
            "trade_count": len(trade_rows),
            "raw_fill_count": 2 * len(trade_rows),
            "files": {trades.name: file_evidence(trades)},
        },
    )


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip_text_writer(path) as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _trade(timestamp: datetime) -> dict[str, object]:
    return {
        "aggressor_side": "buy",
        "price": "100" if timestamp.minute == 0 else "101",
        "size": "1",
        "source": "0xarchive_hyperliquid_public_trades",
        "symbol": "SOL",
        "trade_id": 100 + timestamp.minute,
        "trade_id_source": "vendor",
        "ts_exchange_ms": int(timestamp.timestamp() * 1000),
        "vendor_request_id": "request",
    }


def _candle(
    timestamp: datetime,
    price: float,
    volume: float,
    trade_count: int,
) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": volume,
        "trade_count": trade_count,
    }
