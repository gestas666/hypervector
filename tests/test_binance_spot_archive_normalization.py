"""Tests for outcome-blind Binance spot archive normalization."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from hypervector.research.binance_spot_archive_acquisition import (
    acquire_binance_spot_kline_bundle,
    monthly_spot_kline_archives,
)
import hypervector.research.binance_spot_archive_normalization as normalization


def test_binance_spot_archive_normalization_module_exists() -> None:
    """The checksum-bound source needs a separate normalization boundary."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.binance_spot_archive_normalization"
        )
        is not None
    )


def test_loader_normalizes_microseconds_and_reports_gaps(tmp_path: Path) -> None:
    """Exact UTC minutes and missing-minute boundaries must remain explicit."""
    assert hasattr(normalization, "load_verified_binance_spot_klines")
    source = _source_bundle(
        tmp_path,
        {
            "2025-07": [
                _row("2025-07-28T00:00:00Z", 100.0),
                _row("2025-07-28T00:01:00Z", 101.0),
                _row("2025-07-28T00:03:00Z", 102.0),
            ],
            "2025-08": [
                _row("2025-08-01T00:00:00Z", 103.0),
                _row("2025-08-01T00:01:00Z", 104.0),
            ],
        },
    )

    result = normalization.load_verified_binance_spot_klines(source)

    assert list(result.bars.index) == list(
        pd.to_datetime(
            [
                "2025-07-28T00:00:00Z",
                "2025-07-28T00:01:00Z",
                "2025-07-28T00:03:00Z",
                "2025-08-01T00:00:00Z",
                "2025-08-01T00:01:00Z",
            ],
            utc=True,
        )
    )
    assert result.bars["gap_before_bars"].tolist() == [0, 0, 1, 5756, 0]
    assert result.coverage["rows"] == 5
    assert result.coverage["gap_boundaries"] == 2
    assert result.coverage["missing_minutes"] == 5757
    assert result.coverage["candidate_outcomes_computed"] is False
    assert set(result.bars["source"]) == {"binance_spot_data_vision"}


def test_loader_rejects_duplicate_timestamp_across_archives(tmp_path: Path) -> None:
    """Duplicate cross-month minutes must fail instead of being deduplicated."""
    assert hasattr(normalization, "load_verified_binance_spot_klines")
    duplicate = _row("2025-07-28T00:00:00Z", 100.0)
    source = _source_bundle(
        tmp_path,
        {"2025-07": [duplicate, duplicate], "2025-08": []},
    )

    with pytest.raises(ValueError, match="duplicate open timestamps"):
        normalization.load_verified_binance_spot_klines(source)


def test_loader_rejects_millisecond_timestamp_in_microsecond_archive(
    tmp_path: Path,
) -> None:
    """A 1000x timestamp-unit error must be an explicit technical failure."""
    assert hasattr(normalization, "load_verified_binance_spot_klines")
    row = _row("2025-07-28T00:00:00Z", 100.0)
    row[0] = str(int(row[0]) // 1000)
    source = _source_bundle(tmp_path, {"2025-07": [row], "2025-08": []})

    with pytest.raises(ValueError, match="microseconds"):
        normalization.load_verified_binance_spot_klines(source)


def test_normalized_bundle_is_immutable_and_outcome_blind(tmp_path: Path) -> None:
    """Normalized source publication must bind evidence without signal fields."""
    assert hasattr(normalization, "publish_normalized_binance_spot_bundle")
    source = _source_bundle(
        tmp_path,
        {
            "2025-07": [_row("2025-07-28T00:00:00Z", 100.0)],
            "2025-08": [_row("2025-08-01T00:00:00Z", 101.0)],
        },
    )
    output = tmp_path / "normalized"

    published = normalization.publish_normalized_binance_spot_bundle(source, output)

    assert published == output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(output / "spot_1m.parquet")
    assert manifest["schema_version"] == "normalized_binance_spot_1m_bundle_v1"
    assert manifest["execution_authority"] == "none"
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["coverage"]["rows"] == 2
    assert set(frame) == {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "gap_before_bars",
        "source",
        "source_archive",
    }
    with pytest.raises(FileExistsError, match="already exists"):
        normalization.publish_normalized_binance_spot_bundle(source, output)


def _source_bundle(
    tmp_path: Path,
    monthly_rows: dict[str, list[list[str]]],
) -> Path:
    start = datetime(2025, 7, 28, tzinfo=UTC)
    end = datetime(2025, 8, 1, 0, 2, tzinfo=UTC)
    responses: dict[str, bytes] = {}
    for spec in monthly_spot_kline_archives(start, end):
        rows = monthly_rows.get(spec.month, [])
        content = _zip_bytes(spec.month, rows)
        digest = hashlib.sha256(content).hexdigest()
        responses[spec.url] = content
        responses[spec.checksum_url] = f"{digest}  {spec.filename}\n".encode()
    output = tmp_path / "source"
    return acquire_binance_spot_kline_bundle(
        output,
        start,
        end,
        responses.__getitem__,
    )


def _zip_bytes(month: str, rows: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    name = f"BTCUSDT-1m-{month}.csv"
    content = "".join(",".join(row) + "\n" for row in rows)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def _row(timestamp: str, close: float) -> list[str]:
    opened = pd.Timestamp(timestamp)
    open_us = opened.value // 1000
    close_us = open_us + 60_000_000 - 1
    return [
        str(open_us),
        str(close - 0.5),
        str(close + 1.0),
        str(close - 1.0),
        str(close),
        "10.0",
        str(close_us),
        "1000.0",
        "5",
        "6.0",
        "600.0",
        "0",
    ]
