"""Tests for verified multi-partition 0xArchive mark-price loading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest
import hypervector.data.oxa_price_archive as price_archive

from hypervector.data.oxa_price_archive import (
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_prices import (
    OxaPriceFetch,
    OxaPricePage,
    OxaPriceRequest,
    OxaPriceSnapshot,
    price_output_directory,
    store_price_history,
)


def _fixture(tmp_path: Path) -> OxaPriceArchiveConfig:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(seconds=4)
    config = OxaPriceArchiveConfig(
        "SOL",
        start,
        end,
        tmp_path,
        chunk=timedelta(seconds=2),
        maximum_gap=timedelta(seconds=1),
    )
    for offset in (0, 2):
        left = start + timedelta(seconds=offset)
        right = left + timedelta(seconds=2)
        request = OxaPriceRequest("SOL", left, right)
        snapshots = tuple(
            OxaPriceSnapshot(
                (left + timedelta(milliseconds=500 + index * 1_000)).isoformat(),
                int(
                    (left + timedelta(milliseconds=500 + index * 1_000)).timestamp()
                    * 1_000
                ),
                str(100.0 + offset + index),
                str(100.1 + offset + index),
                str(100.05 + offset + index),
            )
            for index in range(2)
        )
        page = OxaPricePage("request", None, snapshots, {"success": True})
        store_price_history(
            tmp_path,
            request,
            OxaPriceFetch((page,), snapshots, True, None),
        )
    return config


def test_price_archive_loads_verified_contiguous_partitions(tmp_path: Path) -> None:
    """All immutable partitions must combine into one unique causal series."""
    archive = load_verified_price_archive(_fixture(tmp_path))

    assert len(archive.frame) == 4
    assert archive.frame["ts_ms"].is_monotonic_increasing
    assert archive.frame["ts_ms"].is_unique
    assert archive.frame["mark_price"].tolist() == [100.0, 101.0, 102.0, 103.0]
    assert archive.maximum_observed_gap_ms == 1_000
    assert archive.partition_count == 2


def test_price_archive_materializes_verified_parts_without_refetch(
    tmp_path: Path,
) -> None:
    """Verified partitions can publish one replay-context bundle locally."""
    config = _fixture(tmp_path)
    materialize = getattr(
        price_archive,
        "materialize_verified_price_archive",
        None,
    )
    assert callable(materialize), "price archive materializer is missing"

    stored = materialize(config)

    combined = load_verified_price_archive(
        OxaPriceArchiveConfig(
            config.symbol,
            config.start,
            config.end,
            config.data_root,
            chunk=config.end - config.start,
            maximum_gap=config.maximum_gap,
        )
    )
    manifest = json.loads(stored.manifest_path.read_text())
    assert combined.frame["mark_price"].tolist() == [100.0, 101.0, 102.0, 103.0]
    assert manifest["materialized_partition_count"] == 2
    assert manifest["row_count"] == 4
    assert manifest["complete"] is True


def test_price_archive_rejects_missing_partition(tmp_path: Path) -> None:
    """A missing requested window must fail instead of shrinking coverage."""
    config = _fixture(tmp_path)
    second = OxaPriceRequest(
        "SOL",
        config.start + timedelta(seconds=2),
        config.end,
    )
    directory = price_output_directory(tmp_path, second)
    directory.rename(directory.with_name(directory.name + "_missing"))

    with pytest.raises(FileNotFoundError, match="missing"):
        load_verified_price_archive(config)


def test_price_archive_rejects_manifest_identity_tampering(tmp_path: Path) -> None:
    """A valid-looking directory with changed identity is not trusted."""
    config = _fixture(tmp_path)
    request = OxaPriceRequest("SOL", config.start, config.start + config.chunk)
    manifest_path = price_output_directory(tmp_path, request) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["symbol"] = "BTC"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="identity"):
        load_verified_price_archive(config)


def test_price_archive_rejects_boundary_gap(tmp_path: Path) -> None:
    """A large unobserved edge interval must not pass internal-gap checks."""
    config = _fixture(tmp_path)
    strict = OxaPriceArchiveConfig(
        config.symbol,
        config.start,
        config.end,
        config.data_root,
        chunk=config.chunk,
        maximum_gap=timedelta(milliseconds=400),
    )

    with pytest.raises(ValueError, match="gap"):
        load_verified_price_archive(strict)


def test_price_archive_report_only_gap_policy_retains_verified_rows(
    tmp_path: Path,
) -> None:
    """Known vendor gaps may be retained for lifecycle-level censoring."""
    config = _fixture(tmp_path)
    report_only = OxaPriceArchiveConfig(
        config.symbol,
        config.start,
        config.end,
        config.data_root,
        chunk=config.chunk,
        maximum_gap=None,
    )

    archive = load_verified_price_archive(report_only)

    assert archive.row_count == 4
    assert archive.maximum_observed_gap_ms == 1_000


def test_price_archive_reports_explicit_empty_partition_ranges(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    config = OxaPriceArchiveConfig(
        "xyz:MU",
        start,
        start + timedelta(hours=3),
        tmp_path,
        chunk=timedelta(hours=1),
        maximum_gap=None,
        market_family="hip3",
    )
    for offset in range(3):
        left = start + timedelta(hours=offset)
        right = left + timedelta(hours=1)
        request = OxaPriceRequest("xyz:MU", left, right, market_family="hip3")
        snapshots = (
            ()
            if offset == 1
            else (
                OxaPriceSnapshot(
                    (left + timedelta(minutes=30)).isoformat(),
                    int((left + timedelta(minutes=30)).timestamp() * 1_000),
                    "100.0",
                    "100.1",
                    "100.05",
                ),
            )
        )
        page = OxaPricePage("request", None, snapshots, {"success": True})
        store_price_history(
            tmp_path,
            request,
            OxaPriceFetch((page,), snapshots, True, None),
        )

    archive = load_verified_price_archive(config)

    assert archive.empty_partition_count == 1
    assert archive.empty_partition_ranges_utc == (
        (
            "2026-01-01T01:00:00+00:00",
            "2026-01-01T02:00:00+00:00",
        ),
    )


def test_price_archive_retains_and_reports_missing_mark_observations(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    config = OxaPriceArchiveConfig(
        "xyz:MU",
        start,
        start + timedelta(seconds=4),
        tmp_path,
        chunk=timedelta(seconds=2),
        maximum_gap=None,
        market_family="hip3",
    )
    for offset, mark in ((0, None), (2, "101.0")):
        left = start + timedelta(seconds=offset)
        right = left + timedelta(seconds=2)
        request = OxaPriceRequest("xyz:MU", left, right, market_family="hip3")
        timestamp = left + timedelta(milliseconds=500)
        snapshots = (
            OxaPriceSnapshot(
                timestamp.isoformat(),
                int(timestamp.timestamp() * 1_000),
                mark,
                "100.0",
                "100.1",
            ),
        )
        page = OxaPricePage("request", None, snapshots, {"success": True})
        store_price_history(
            tmp_path,
            request,
            OxaPriceFetch((page,), snapshots, True, None),
        )

    archive = load_verified_price_archive(config)

    assert archive.row_count == 2
    assert archive.mark_row_count == 1
    assert archive.missing_mark_row_count == 1
    assert archive.oracle_row_count == 2
    assert archive.maximum_observed_gap_ms == 2_500
