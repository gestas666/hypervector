"""Immutable official Hyperliquid funding-history evidence bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.data.hl import (
    HL_INFO_URL,
    fetch_hl_funding_pages,
    funding_from_hl_payload,
)
from hypervector.data.oxa_api import (
    validate_hip3_symbol,
    validate_symbol,
    validate_window,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_gzip_json,
    write_json,
)

_SOURCE = "hl_funding_history"


@dataclass(frozen=True)
class HlFundingRequest:
    """Exact half-open hourly window for official funding evidence."""

    symbol: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if ":" in self.symbol:
            validate_hip3_symbol(self.symbol)
        else:
            validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        if not _hour_aligned(self.start) or not _hour_aligned(self.end):
            raise ValueError("funding archive bounds must be hour-aligned")


@dataclass(frozen=True)
class HlStoredFunding:
    """Published official funding evidence paths."""

    directory: Path
    funding_path: Path
    manifest_path: Path


def funding_output_directory(data_root: Path | str, request: HlFundingRequest) -> Path:
    """Return the immutable directory for one funding-history window."""
    stamp = "%Y%m%dT%H%M%S%fZ"
    window = f"{request.start.strftime(stamp)}_{request.end.strftime(stamp)}"
    return (
        Path(data_root)
        / "cache"
        / "vendor"
        / "hyperliquid"
        / request.symbol
        / f"{window}_funding"
    )


def store_hl_funding(
    data_root: Path | str,
    request: HlFundingRequest,
    pages: tuple[tuple[dict[str, Any], ...], ...],
) -> HlStoredFunding:
    """Validate and atomically publish raw and normalized funding evidence."""
    frame = _normalized_window(request, pages)
    coverage = _coverage(request, frame)
    missing = int(coverage["missing_hour_count"])
    if missing:
        raise ValueError(f"funding history is missing {missing} hourly settlement(s)")
    final = funding_output_directory(data_root, request)

    def write_bundle(staging: Path) -> None:
        files = _write_raw_pages(staging, pages)
        funding_path = staging / "funding.parquet"
        frame.to_parquet(funding_path, index=False)
        files[funding_path.name] = file_evidence(funding_path)
        manifest = _manifest(request, pages, coverage, files)
        write_json(staging / "manifest.json", manifest)

    publish_immutable_directory(final, write_bundle)
    return HlStoredFunding(final, final / "funding.parquet", final / "manifest.json")


def acquire_and_store_hl_funding(
    *, data_root: Path | str, request: HlFundingRequest
) -> dict[str, object]:
    """Acquire a complete official window and return its evidence report."""
    pages = fetch_hl_funding_pages(
        request.symbol,
        start_time=pd.Timestamp(request.start),
        end_time=pd.Timestamp(request.end),
    )
    stored = store_hl_funding(data_root, request, pages)
    frame = pd.read_parquet(stored.funding_path)
    return {
        "ok": True,
        "venue": "hyperliquid",
        "source": _SOURCE,
        "symbol": request.symbol,
        "row_count": len(frame),
        "page_count": len(pages),
        "complete": True,
        "directory": str(stored.directory.resolve()),
        "funding_path": str(stored.funding_path.resolve()),
        "manifest_path": str(stored.manifest_path.resolve()),
    }


def _normalized_window(
    request: HlFundingRequest,
    pages: tuple[tuple[dict[str, Any], ...], ...],
) -> pd.DataFrame:
    raw = [row for page in pages for row in page]
    frame = funding_from_hl_payload(raw)
    frame = frame.merge(_event_times(raw), on="timestamp", validate="one_to_one")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    start, end = pd.Timestamp(request.start), pd.Timestamp(request.end)
    return frame.loc[(timestamps >= start) & (timestamps < end)].reset_index(drop=True)


def _event_times(raw: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "timestamp": pd.to_datetime(int(row["time"]), unit="ms", utc=True).floor(
                "h"
            ),
            "event_ts_ms": int(row["time"]),
        }
        for row in raw
    ]
    frame = pd.DataFrame(rows, columns=["timestamp", "event_ts_ms"])
    if frame["timestamp"].duplicated().any():
        raise ValueError("funding history has duplicate hourly event timestamps")
    return frame


def _coverage(request: HlFundingRequest, frame: pd.DataFrame) -> dict[str, object]:
    expected = pd.date_range(
        request.start, request.end, freq="h", inclusive="left", tz="UTC"
    )
    observed = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    missing = expected.difference(observed)
    return {
        "complete": len(missing) == 0,
        "expected_hour_count": len(expected),
        "observed_hour_count": len(observed),
        "missing_hour_count": len(missing),
        "first_observed": observed.min().isoformat() if len(observed) else None,
        "last_observed": observed.max().isoformat() if len(observed) else None,
    }


def _write_raw_pages(
    staging: Path, pages: tuple[tuple[dict[str, Any], ...], ...]
) -> dict[str, dict[str, object]]:
    raw_dir = staging / "raw"
    raw_dir.mkdir()
    evidence: dict[str, dict[str, object]] = {}
    for index, page in enumerate(pages, start=1):
        path = raw_dir / f"page-{index:04d}.json.gz"
        write_gzip_json(path, list(page))
        evidence[f"raw/{path.name}"] = file_evidence(path)
    return evidence


def _manifest(
    request: HlFundingRequest,
    pages: tuple[tuple[dict[str, Any], ...], ...],
    coverage: dict[str, object],
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": _SOURCE,
        "source_api": HL_INFO_URL,
        "venue": "hyperliquid",
        "symbol": request.symbol,
        "requested_start": request.start.isoformat(),
        "requested_end": request.end.isoformat(),
        "page_count": len(pages),
        **coverage,
        "files": files,
    }


def _hour_aligned(value: datetime) -> bool:
    return not any((value.minute, value.second, value.microsecond))
