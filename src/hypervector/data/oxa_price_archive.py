"""Verified multi-partition loading for 0xArchive mark-price evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.data.oxa_api import (
    MarketFamily,
    validate_market_symbol,
    validate_window,
)
from hypervector.data.oxa_prices import (
    OxaPriceRequest,
    OxaStoredPrices,
    price_output_directory,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)

_SOURCE = "0xarchive_hyperliquid_prices"


@dataclass(frozen=True)
class OxaPriceArchiveConfig:
    """Expected partitioning and optional global mark-gap enforcement."""

    symbol: str
    start: datetime
    end: datetime
    data_root: Path
    chunk: timedelta = timedelta(days=1)
    maximum_gap: timedelta | None = timedelta(minutes=2)
    market_family: MarketFamily = "core"

    def __post_init__(self) -> None:
        """Reject invalid archive bounds before filesystem access."""
        validate_market_symbol(self.symbol, self.market_family)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("price archive chunk must be positive")
        if self.maximum_gap is not None and self.maximum_gap <= timedelta(0):
            raise ValueError("price archive maximum_gap must be positive")


@dataclass(frozen=True)
class OxaPriceArchive:
    """One verified continuous sampled mark/oracle/mid series."""

    frame: pd.DataFrame
    partition_count: int
    row_count: int
    maximum_observed_gap_ms: int
    empty_partition_count: int
    empty_partition_ranges_utc: tuple[tuple[str, str], ...]
    mark_row_count: int
    missing_mark_row_count: int
    oracle_row_count: int
    missing_oracle_row_count: int


def load_verified_price_archive(config: OxaPriceArchiveConfig) -> OxaPriceArchive:
    """Load every expected immutable partition and enforce causal coverage."""
    frames: list[pd.DataFrame] = []
    partition_count = 0
    empty_ranges: list[tuple[datetime, datetime]] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        frame = _load_partition(config, start, end)
        frames.append(frame)
        if frame.empty:
            empty_ranges.append((start, end))
        partition_count += 1
        start = end
    combined = pd.concat(frames, ignore_index=True)
    normalized = _normalize(combined, config)
    maximum_gap_ms = _maximum_gap_ms(normalized, config)
    mark_rows = int(normalized["mark_price"].notna().sum())
    oracle_rows = int(normalized["oracle_price"].notna().sum())
    return OxaPriceArchive(
        normalized,
        partition_count,
        len(normalized),
        maximum_gap_ms,
        len(empty_ranges),
        _serialize_ranges(_coalesce_ranges(empty_ranges)),
        mark_rows,
        len(normalized) - mark_rows,
        oracle_rows,
        len(normalized) - oracle_rows,
    )


def materialize_verified_price_archive(
    config: OxaPriceArchiveConfig,
) -> OxaStoredPrices:
    """Publish one immutable replay bundle from verified local partitions."""
    archive = load_verified_price_archive(config)
    request = OxaPriceRequest(
        config.symbol,
        config.start,
        config.end,
        market_family=config.market_family,
    )
    final = price_output_directory(config.data_root, request)
    partitions = _partition_manifest_evidence(config)

    def write_bundle(staging: Path) -> None:
        prices_path = staging / "prices.parquet"
        archive.frame.to_parquet(prices_path, index=False)
        files = {"prices.parquet": file_evidence(prices_path)}
        write_json(
            staging / "manifest.json",
            _materialized_manifest(config, archive, partitions, files),
        )

    publish_immutable_directory(final, write_bundle)
    return OxaStoredPrices(final, final / "prices.parquet", final / "manifest.json")


def _partition_manifest_evidence(
    config: OxaPriceArchiveConfig,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        directory = price_output_directory(
            config.data_root,
            OxaPriceRequest(
                config.symbol, start, end, market_family=config.market_family
            ),
        )
        manifest = directory / "manifest.json"
        evidence.append({"path": str(manifest.resolve()), **file_evidence(manifest)})
        start = end
    return evidence


def _materialized_manifest(
    config: OxaPriceArchiveConfig,
    archive: OxaPriceArchive,
    partitions: list[dict[str, object]],
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": _SOURCE,
        "venue": "hyperliquid",
        "symbol": config.symbol,
        "requested_start": config.start.isoformat(),
        "requested_end": config.end.isoformat(),
        "complete": True,
        "row_count": archive.row_count,
        "materialized_partition_count": archive.partition_count,
        "maximum_observed_gap_ms": archive.maximum_observed_gap_ms,
        "empty_partition_count": archive.empty_partition_count,
        "empty_partition_ranges_utc": archive.empty_partition_ranges_utc,
        "mark_row_count": archive.mark_row_count,
        "missing_mark_row_count": archive.missing_mark_row_count,
        "oracle_row_count": archive.oracle_row_count,
        "missing_oracle_row_count": archive.missing_oracle_row_count,
        "maximum_allowed_gap_ms": (
            None
            if config.maximum_gap is None
            else int(config.maximum_gap.total_seconds() * 1_000)
        ),
        "gap_enforcement": ("report_only" if config.maximum_gap is None else "bounded"),
        "materialization_method": "verified_local_partitions",
        "partition_manifests": partitions,
        "files": files,
    }


def _load_partition(
    config: OxaPriceArchiveConfig,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    request = OxaPriceRequest(
        config.symbol, start, end, market_family=config.market_family
    )
    directory = price_output_directory(config.data_root, request)
    if not directory.is_dir():
        raise FileNotFoundError(f"price archive partition is missing: {directory}")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"price archive manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_identity(manifest, config.symbol, start, end, directory)
    verify_file_evidence(directory, manifest.get("files"))
    frame = pd.read_parquet(directory / "prices.parquet")
    expected_rows = manifest.get("row_count")
    if isinstance(expected_rows, bool) or not isinstance(expected_rows, int):
        raise ValueError(f"price archive row_count is invalid: {directory}")
    if len(frame) != expected_rows:
        raise ValueError(f"price archive row-count mismatch: {directory}")
    return frame


def _validate_identity(
    manifest: object,
    symbol: str,
    start: datetime,
    end: datetime,
    directory: Path,
) -> None:
    if not isinstance(manifest, dict):
        raise ValueError(f"price archive manifest must be an object: {directory}")
    expected = {
        "complete": True,
        "source": _SOURCE,
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"price archive manifest identity mismatch: {directory}")


def _normalize(
    frame: pd.DataFrame,
    config: OxaPriceArchiveConfig,
) -> pd.DataFrame:
    required = {"ts_ms", "mark_price", "oracle_price", "mid_price", "source"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"price archive is missing columns: {sorted(missing)}")
    result = frame.copy()
    result["ts_ms"] = pd.to_numeric(result["ts_ms"], errors="raise").astype("int64")
    for column in ("mark_price", "oracle_price", "mid_price"):
        raw = result[column]
        parsed = pd.to_numeric(raw, errors="coerce")
        if (raw.notna() & parsed.isna()).any() or parsed.dropna().le(0.0).any():
            raise ValueError(f"price archive {column} must be positive when present")
        result[column] = parsed
    result = result.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    if result["ts_ms"].duplicated().any():
        raise ValueError("price archive timestamps must be unique")
    start_ms, end_ms = _datetime_ms(config.start), _datetime_ms(config.end)
    if ((result["ts_ms"] < start_ms) | (result["ts_ms"] >= end_ms)).any():
        raise ValueError("price archive contains timestamps outside requested bounds")
    return result


def _maximum_gap_ms(
    frame: pd.DataFrame,
    config: OxaPriceArchiveConfig,
) -> int:
    marks = frame.loc[frame["mark_price"].notna(), "ts_ms"]
    if marks.empty and config.maximum_gap is not None:
        raise ValueError("price archive contains no mark observations")
    if frame.empty:
        raise ValueError("price archive contains no mark observations")
    start_ms, end_ms = _datetime_ms(config.start), _datetime_ms(config.end)
    if marks.empty:
        return end_ms - start_ms
    timestamps = marks.to_numpy(dtype=np.int64)
    internal = int(np.diff(timestamps).max()) if len(timestamps) > 1 else 0
    maximum = max(int(timestamps[0] - start_ms), internal, int(end_ms - timestamps[-1]))
    if config.maximum_gap is not None:
        allowed = int(config.maximum_gap.total_seconds() * 1_000)
        if maximum > allowed:
            raise ValueError(f"price archive gap {maximum}ms exceeds {allowed}ms")
    return maximum


def _datetime_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _coalesce_ranges(
    ranges: list[tuple[datetime, datetime]],
) -> tuple[tuple[datetime, datetime], ...]:
    if not ranges:
        return ()
    output: list[tuple[datetime, datetime]] = [ranges[0]]
    for start, end in ranges[1:]:
        prior_start, prior_end = output[-1]
        if start == prior_end:
            output[-1] = (prior_start, end)
        else:
            output.append((start, end))
    return tuple(output)


def _serialize_ranges(
    ranges: tuple[tuple[datetime, datetime], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((start.isoformat(), end.isoformat()) for start, end in ranges)
