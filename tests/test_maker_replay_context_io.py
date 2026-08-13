"""Verified immutable replay-context loading and coverage tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.research.maker_replay_context_io import (
    context_coverage_report,
    load_verified_replay_context,
    load_verified_replay_context_parts,
)

_START = "2026-01-01T00:00:00+00:00"
_END = "2026-01-01T02:00:00+00:00"


def _bundle(
    root: Path,
    filename: str,
    source: str,
    frame: pd.DataFrame,
    *,
    directory_name: str | None = None,
    start: str = _START,
    end: str = _END,
) -> Path:
    directory = root / (directory_name or source)
    directory.mkdir()
    path = directory / filename
    frame.to_parquet(path, index=False)
    write_json(
        directory / "manifest.json",
        {
            "complete": True,
            "source": source,
            "requested_start": start,
            "requested_end": end,
            "files": {filename: file_evidence(path)},
        },
    )
    return path


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    prices = pd.DataFrame(
        {
            "ts_ms": [1_767_225_600_000, 1_767_225_660_000],
            "mark_price": [100.0, 101.0],
            "oracle_price": [100.0, 101.0],
        }
    )
    funding = pd.DataFrame(
        {"event_ts_ms": [1_767_225_600_030], "funding_rate": [0.00001]}
    )
    return (
        _bundle(tmp_path, "prices.parquet", "0xarchive_hyperliquid_prices", prices),
        _bundle(tmp_path, "funding.parquet", "hl_funding_history", funding),
    )


def test_verified_context_loader_checks_identity_bounds_and_files(
    tmp_path: Path,
) -> None:
    """Only checksum-verified context with matching windows is replayable."""
    price_path, funding_path = _paths(tmp_path)

    context = load_verified_replay_context(price_path, funding_path)
    report = context_coverage_report(context)

    assert len(context.prices) == 2
    assert report["price_rows"] == 2
    assert report["maximum_price_gap_seconds"] == 60.0
    assert report["funding_rows"] == 1
    assert report["checksums_verified"] is True


def test_context_coverage_reports_largest_price_gap_boundaries(
    tmp_path: Path,
) -> None:
    """A replay report identifies the exact unresolved mark-price interval."""
    prices = pd.DataFrame(
        {
            "ts_ms": [1_767_225_600_000, 1_767_225_840_000],
            "mark_price": [100.0, 101.0],
            "oracle_price": [100.0, 101.0],
        }
    )
    funding = pd.DataFrame(
        {"event_ts_ms": [1_767_225_600_030], "funding_rate": [0.00001]}
    )
    context = load_verified_replay_context(
        _bundle(
            tmp_path,
            "prices.parquet",
            "0xarchive_hyperliquid_prices",
            prices,
            directory_name="gap-prices",
        ),
        _bundle(
            tmp_path,
            "funding.parquet",
            "hl_funding_history",
            funding,
            directory_name="gap-funding",
        ),
    )

    report = context_coverage_report(context)

    assert report["maximum_price_gap_seconds"] == 240.0
    assert report["maximum_price_gap_start_utc"] == "2026-01-01T00:00:00+00:00"
    assert report["maximum_price_gap_end_utc"] == "2026-01-01T00:04:00+00:00"


def test_verified_context_loader_rejects_tampered_evidence(tmp_path: Path) -> None:
    """A post-manifest mutation cannot become replay evidence."""
    price_path, funding_path = _paths(tmp_path)
    funding_path.write_bytes(funding_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="byte count mismatch"):
        load_verified_replay_context(price_path, funding_path)


def test_verified_context_loader_combines_contiguous_parts(tmp_path: Path) -> None:
    """Verified adjacent bundles form one causal chronology without copying."""
    middle = "2026-01-01T01:00:00+00:00"
    price_one = _bundle(
        tmp_path,
        "prices.parquet",
        "0xarchive_hyperliquid_prices",
        pd.DataFrame({"ts_ms": [1], "mark_price": [100.0], "oracle_price": [100.0]}),
        directory_name="prices-one",
        start=_START,
        end=middle,
    )
    funding_one = _bundle(
        tmp_path,
        "funding.parquet",
        "hl_funding_history",
        pd.DataFrame({"event_ts_ms": [2], "funding_rate": [0.00001]}),
        directory_name="funding-one",
        start=_START,
        end=middle,
    )
    price_two = _bundle(
        tmp_path,
        "prices.parquet",
        "0xarchive_hyperliquid_prices",
        pd.DataFrame({"ts_ms": [3], "mark_price": [101.0], "oracle_price": [101.0]}),
        directory_name="prices-two",
        start=middle,
        end=_END,
    )
    funding_two = _bundle(
        tmp_path,
        "funding.parquet",
        "hl_funding_history",
        pd.DataFrame({"event_ts_ms": [4], "funding_rate": [0.00002]}),
        directory_name="funding-two",
        start=middle,
        end=_END,
    )

    context = load_verified_replay_context_parts(
        ((price_one, funding_one), (price_two, funding_two))
    )

    assert context.prices["ts_ms"].tolist() == [1, 3]
    assert context.funding["event_ts_ms"].tolist() == [2, 4]


def test_verified_context_loader_rejects_part_gap(tmp_path: Path) -> None:
    """Segment manifest bounds must cover one contiguous outer interval."""
    price_path, funding_path = _paths(tmp_path)
    late_start = "2026-01-01T03:00:00+00:00"
    late_end = "2026-01-01T04:00:00+00:00"
    late_price = _bundle(
        tmp_path,
        "prices.parquet",
        "0xarchive_hyperliquid_prices",
        pd.DataFrame({"ts_ms": [5], "mark_price": [102.0], "oracle_price": [102.0]}),
        directory_name="late-prices",
        start=late_start,
        end=late_end,
    )
    late_funding = _bundle(
        tmp_path,
        "funding.parquet",
        "hl_funding_history",
        pd.DataFrame({"event_ts_ms": [6], "funding_rate": [0.00003]}),
        directory_name="late-funding",
        start=late_start,
        end=late_end,
    )

    with pytest.raises(ValueError, match="not contiguous"):
        load_verified_replay_context_parts(
            ((price_path, funding_path), (late_price, late_funding))
        )
