"""Checksum-bound Binance spot archive acquisition for BTC research."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)


_BASE_URL = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m"
_SCHEMA_VERSION = "binance_spot_kline_archive_bundle_v1"


@dataclass(frozen=True)
class BinanceSpotArchiveSpec:
    """Identify one official monthly BTCUSDT spot one-minute archive."""

    month: str
    filename: str
    url: str
    checksum_url: str


def monthly_spot_kline_archives(
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[BinanceSpotArchiveSpec, ...]:
    """Return every official monthly archive intersecting an exclusive window."""
    start, end = _validated_window(start_utc, end_utc)
    month = datetime(start.year, start.month, 1, tzinfo=UTC)
    last = end - timedelta(microseconds=1)
    values: list[BinanceSpotArchiveSpec] = []
    while month <= last:
        month_id = month.strftime("%Y-%m")
        filename = f"BTCUSDT-1m-{month_id}.zip"
        url = f"{_BASE_URL}/{filename}"
        values.append(
            BinanceSpotArchiveSpec(month_id, filename, url, f"{url}.CHECKSUM")
        )
        month = _next_month(month)
    return tuple(values)


def acquire_binance_spot_kline_bundle(
    output: Path,
    start_utc: datetime,
    end_utc: datetime,
    fetch_bytes: Callable[[str], bytes],
    *,
    context: dict[str, object] | None = None,
) -> Path:
    """Fetch, verify, and atomically publish a report-only vendor bundle."""
    start, end = _validated_window(start_utc, end_utc)
    specs = monthly_spot_kline_archives(start, end)
    if output.exists():
        raise FileExistsError(f"Binance spot archive bundle already exists: {output}")
    bound_context = dict(context or {})

    def writer(staging: Path) -> None:
        _write_bundle(staging, start, end, specs, fetch_bytes, bound_context)

    publish_immutable_directory(output, writer)
    return output


def _write_bundle(
    staging: Path,
    start: datetime,
    end: datetime,
    specs: tuple[BinanceSpotArchiveSpec, ...],
    fetch_bytes: Callable[[str], bytes],
    context: dict[str, object],
) -> None:
    vendor = staging / "vendor"
    vendor.mkdir()
    archives: dict[str, dict[str, object]] = {}
    for spec in specs:
        content = _fetched_bytes(fetch_bytes, spec.url)
        checksum_content = _fetched_bytes(fetch_bytes, spec.checksum_url)
        expected = _vendor_checksum(checksum_content, spec.filename)
        observed = hashlib.sha256(content).hexdigest()
        if observed != expected:
            raise ValueError(
                f"Binance vendor checksum mismatch for {spec.filename}: "
                f"expected {expected}, observed {observed}"
            )
        archive_path = vendor / spec.filename
        checksum_path = vendor / f"{spec.filename}.CHECKSUM"
        archive_path.write_bytes(content)
        checksum_path.write_bytes(checksum_content)
        archives[spec.filename] = _archive_record(
            spec, archive_path, checksum_path, expected
        )
    write_json(staging / "manifest.json", _manifest(start, end, archives, context))


def _manifest(
    start: datetime,
    end: datetime,
    archives: dict[str, dict[str, object]],
    context: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "binance_data_vision_spot_monthly_klines",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "archive_count": len(archives),
        "archives": archives,
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
        "context": context,
    }


def _archive_record(
    spec: BinanceSpotArchiveSpec,
    archive_path: Path,
    checksum_path: Path,
    expected: str,
) -> dict[str, object]:
    return {
        "month": spec.month,
        "source_url": spec.url,
        "checksum_url": spec.checksum_url,
        "vendor_sha256": expected,
        "archive_file": f"vendor/{spec.filename}",
        "archive_evidence": file_evidence(archive_path),
        "checksum_file": f"vendor/{spec.filename}.CHECKSUM",
        "checksum_evidence": file_evidence(checksum_path),
    }


def _validated_window(
    start_utc: datetime, end_utc: datetime
) -> tuple[datetime, datetime]:
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("Binance archive bounds must be timezone-aware")
    start = start_utc.astimezone(UTC)
    end = end_utc.astimezone(UTC)
    if end <= start:
        raise ValueError("Binance archive end must be after start")
    return start, end


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=UTC)
    return datetime(value.year, value.month + 1, 1, tzinfo=UTC)


def _fetched_bytes(fetch_bytes: Callable[[str], bytes], url: str) -> bytes:
    content = fetch_bytes(url)
    if not isinstance(content, bytes) or not content:
        raise ValueError(f"Binance archive fetch returned no bytes: {url}")
    return content


def _vendor_checksum(content: bytes, filename: str) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Binance checksum is not UTF-8: {filename}") from exc
    matches = [line.split() for line in text.splitlines() if line.split()]
    for fields in matches:
        if len(fields) == 2 and fields[1].lstrip("*") == filename:
            digest = fields[0].lower()
            if len(digest) == 64 and all(
                value in "0123456789abcdef" for value in digest
            ):
                return digest
    raise ValueError(f"Binance checksum does not bind {filename}")
