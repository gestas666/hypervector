"""Tests for checksum-bound Binance spot archive acquisition."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

import hypervector.research.binance_spot_archive_acquisition as archive


def test_binance_spot_archive_acquisition_module_exists() -> None:
    """The preregistered data-acquisition module must be importable."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.binance_spot_archive_acquisition"
        )
        is not None
    )


def test_monthly_specs_cover_every_intersecting_month() -> None:
    """The frozen interval must bind July 2025 through July 2026."""
    assert hasattr(archive, "monthly_spot_kline_archives")
    specs = archive.monthly_spot_kline_archives(
        datetime(2025, 7, 28, tzinfo=UTC),
        datetime(2026, 7, 28, tzinfo=UTC),
    )

    assert len(specs) == 13
    assert specs[0].filename == "BTCUSDT-1m-2025-07.zip"
    assert specs[-1].filename == "BTCUSDT-1m-2026-07.zip"
    assert specs[0].url == (
        "https://data.binance.vision/data/spot/monthly/klines/"
        "BTCUSDT/1m/BTCUSDT-1m-2025-07.zip"
    )
    assert specs[0].checksum_url == f"{specs[0].url}.CHECKSUM"


def test_monthly_specs_reject_naive_or_reversed_bounds() -> None:
    """Ambiguous or empty acquisition windows must fail before fetching."""
    assert hasattr(archive, "monthly_spot_kline_archives")
    with pytest.raises(ValueError, match="timezone-aware"):
        archive.monthly_spot_kline_archives(
            datetime(2025, 7, 28),
            datetime(2026, 7, 28, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="end must be after start"):
        archive.monthly_spot_kline_archives(
            datetime(2026, 7, 28, tzinfo=UTC),
            datetime(2025, 7, 28, tzinfo=UTC),
        )


def test_acquisition_publishes_checksum_verified_immutable_bundle(
    tmp_path: Path,
) -> None:
    """Fetched bytes and vendor checksums must be retained and manifested."""
    assert hasattr(archive, "acquire_binance_spot_kline_bundle")
    start = datetime(2025, 7, 28, tzinfo=UTC)
    end = datetime(2025, 8, 2, tzinfo=UTC)
    specs = archive.monthly_spot_kline_archives(start, end)
    responses: dict[str, bytes] = {}
    for spec in specs:
        content = f"archive:{spec.filename}".encode()
        digest = hashlib.sha256(content).hexdigest()
        responses[spec.url] = content
        responses[spec.checksum_url] = f"{digest}  {spec.filename}\n".encode()

    output = tmp_path / "bundle"
    observed = archive.acquire_binance_spot_kline_bundle(
        output,
        start,
        end,
        responses.__getitem__,
    )

    assert observed == output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "binance_spot_kline_archive_bundle_v1"
    assert manifest["execution_authority"] == "none"
    assert manifest["archive_count"] == 2
    assert manifest["start_utc"] == "2025-07-28T00:00:00+00:00"
    assert manifest["end_utc"] == "2025-08-02T00:00:00+00:00"
    for spec in specs:
        assert (output / "vendor" / spec.filename).read_bytes() == responses[spec.url]
        assert (output / "vendor" / f"{spec.filename}.CHECKSUM").read_bytes() == (
            responses[spec.checksum_url]
        )
        assert manifest["archives"][spec.filename]["vendor_sha256"] == (
            hashlib.sha256(responses[spec.url]).hexdigest()
        )

    with pytest.raises(FileExistsError, match="already exists"):
        archive.acquire_binance_spot_kline_bundle(
            output,
            start,
            end,
            responses.__getitem__,
        )


def test_acquisition_rejects_vendor_checksum_mismatch(tmp_path: Path) -> None:
    """Corrupt vendor bytes must leave no success-shaped bundle."""
    assert hasattr(archive, "acquire_binance_spot_kline_bundle")
    start = datetime(2025, 7, 28, tzinfo=UTC)
    end = datetime(2025, 7, 29, tzinfo=UTC)
    spec = archive.monthly_spot_kline_archives(start, end)[0]
    responses = {
        spec.url: b"corrupt",
        spec.checksum_url: f"{'0' * 64}  {spec.filename}\n".encode(),
    }
    output = tmp_path / "bundle"

    with pytest.raises(ValueError, match="vendor checksum mismatch"):
        archive.acquire_binance_spot_kline_bundle(
            output,
            start,
            end,
            responses.__getitem__,
        )
    assert not output.exists()


def test_acquisition_manifest_binds_report_only_context(tmp_path: Path) -> None:
    """The immutable vendor bundle must retain its preregistration identity."""
    start = datetime(2025, 7, 28, tzinfo=UTC)
    end = datetime(2025, 7, 29, tzinfo=UTC)
    spec = archive.monthly_spot_kline_archives(start, end)[0]
    content = b"archive"
    digest = hashlib.sha256(content).hexdigest()
    responses = {
        spec.url: content,
        spec.checksum_url: f"{digest}  {spec.filename}\n".encode(),
    }
    context: dict[str, object] = {
        "hypothesis_id": "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1",
        "preregistration": {"sha256": "abc", "bytes": 123},
    }
    output = tmp_path / "bundle"

    archive.acquire_binance_spot_kline_bundle(
        output,
        start,
        end,
        responses.__getitem__,
        context=context,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["context"] == context
