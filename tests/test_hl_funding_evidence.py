"""Read-side validation for immutable official funding bundles."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.hl_funding_archive import HlFundingRequest, store_hl_funding
from hypervector.data.hl_funding_evidence import read_complete_hl_funding_evidence
from hypervector.data.oxa_storage import file_evidence


def test_complete_bundle_is_verified_and_bounds_execution_intervals(
    tmp_path: Path,
) -> None:
    """A replay may consume only checksummed rows inside the manifest window."""
    start_ms = 1_784_980_800_000
    request = HlFundingRequest(
        "BTC",
        datetime(2026, 7, 25, 12, tzinfo=UTC),
        datetime(2026, 7, 25, 14, tzinfo=UTC),
    )
    stored = store_hl_funding(
        tmp_path,
        request,
        (
            (
                _row(start_ms, "0.00001"),
                _row(start_ms + 3_600_000, "-0.00002"),
            ),
        ),
    )

    evidence = read_complete_hl_funding_evidence(stored.funding_path, "BTC")

    assert len(evidence.rows) == 2
    assert evidence.evidence["complete"] is True
    evidence.require_covers(start_ms + 1, start_ms + 3_600_000)
    with pytest.raises(ValueError, match="does not cover"):
        evidence.require_covers(start_ms, start_ms + 7_200_000)


def test_hip3_bundle_preserves_namespaced_symbol_identity(tmp_path: Path) -> None:
    """Funding verification must not uppercase the HIP-3 dex namespace."""
    start_ms = 1_784_980_800_000
    request = HlFundingRequest(
        "xyz:SPCX",
        datetime(2026, 7, 25, 12, tzinfo=UTC),
        datetime(2026, 7, 25, 14, tzinfo=UTC),
    )
    stored = store_hl_funding(
        tmp_path,
        request,
        (
            (
                _row(start_ms, "0.00001", coin="xyz:SPCX"),
                _row(
                    start_ms + 3_600_000,
                    "-0.00002",
                    coin="xyz:SPCX",
                ),
            ),
        ),
    )

    evidence = read_complete_hl_funding_evidence(stored.funding_path, "xyz:SPCX")

    assert evidence.symbol == "xyz:SPCX"
    assert len(evidence.rows) == 2


def test_reader_rejects_checksummed_parquet_with_missing_hour(tmp_path: Path) -> None:
    """A rewritten checksum cannot make incomplete normalized rows complete."""
    stored = _stored_bundle(tmp_path)
    frame = pd.read_parquet(stored.funding_path).iloc[:-1]
    frame.to_parquet(stored.funding_path, index=False)
    manifest = json.loads(stored.manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["funding.parquet"] = file_evidence(stored.funding_path)
    stored.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="hourly coverage"):
        read_complete_hl_funding_evidence(stored.funding_path, "xyz:CL")


def test_reader_rejects_tampered_raw_page(tmp_path: Path) -> None:
    """Every retained raw page remains bound to the consumed normalized file."""
    stored = _stored_bundle(tmp_path)
    raw_path = stored.directory / "raw/page-0001.json.gz"
    raw_path.write_bytes(raw_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="bundle evidence .* mismatch: .*page-0001"):
        read_complete_hl_funding_evidence(stored.funding_path, "xyz:CL")


def test_reader_rejects_raw_symbol_mismatch(tmp_path: Path) -> None:
    """Manifest identity cannot relabel another market's raw funding rows."""
    start_ms = 1_784_980_800_000
    request = HlFundingRequest(
        "xyz:CL",
        datetime(2026, 7, 25, 12, tzinfo=UTC),
        datetime(2026, 7, 25, 14, tzinfo=UTC),
    )
    stored = store_hl_funding(
        tmp_path,
        request,
        (
            (
                _row(start_ms, "0.00001"),
                _row(start_ms + 3_600_000, "-0.00002"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="wrong symbol"):
        read_complete_hl_funding_evidence(stored.funding_path, "xyz:CL")


def _stored_bundle(tmp_path: Path):
    start_ms = 1_784_980_800_000
    request = HlFundingRequest(
        "xyz:CL",
        datetime(2026, 7, 25, 12, tzinfo=UTC),
        datetime(2026, 7, 25, 14, tzinfo=UTC),
    )
    return store_hl_funding(
        tmp_path,
        request,
        (
            (
                _row(start_ms, "0.00001", coin="xyz:CL"),
                _row(start_ms + 3_600_000, "-0.00002", coin="xyz:CL"),
            ),
        ),
    )


def _row(hour_ms: int, rate: str, *, coin: str = "BTC") -> dict[str, object]:
    return {
        "coin": coin,
        "fundingRate": rate,
        "premium": "0.00002",
        "time": hour_ms + 30,
    }
