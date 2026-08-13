"""Verified read-side access to immutable Hyperliquid funding bundles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path

import pandas as pd

from hypervector.data.hl import HL_INFO_URL, hl_coin
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    verify_file_evidence,
)


@dataclass(frozen=True)
class HlFundingEvidence:
    """Complete official funding rows plus their verified half-open bounds."""

    symbol: str
    start_ms: int
    end_ms: int
    rows: tuple[dict[str, object], ...]
    evidence: dict[str, object]

    def require_covers(self, entry_time_ms: int, exit_time_ms: int) -> None:
        """Reject an execution interval not covered by every settlement boundary."""
        if entry_time_ms < self.start_ms or exit_time_ms >= self.end_ms:
            raise ValueError(
                f"{self.symbol} funding evidence does not cover execution interval"
            )

    def require_exact_window(self, start_ms: int, end_ms: int) -> None:
        """Reject funding evidence not bound to the requested half-open window."""
        if (self.start_ms, self.end_ms) != (start_ms, end_ms):
            raise ValueError(
                f"{self.symbol} funding evidence does not match the exact window"
            )

    def to_frame(self) -> pd.DataFrame:
        """Return the verified rows in the official attachment schema."""
        frame = pd.DataFrame(self.rows)
        frame["timestamp"] = pd.to_datetime(
            frame["event_ts_ms"], unit="ms", utc=True
        ).dt.floor("h")
        return frame.loc[:, ["timestamp", "funding_rate", "source", "event_ts_ms"]]


def read_complete_hl_funding_evidence(
    funding_path: Path | str, symbol: str
) -> HlFundingEvidence:
    """Verify one normalized funding file against its immutable manifest."""
    path = Path(funding_path)
    normalized_symbol = hl_coin(symbol)
    if not path.is_file():
        raise FileNotFoundError(f"funding evidence does not exist: {path}")
    manifest_path = path.parent / "manifest.json"
    manifest = _manifest(manifest_path, normalized_symbol)
    verify_file_evidence(path.parent, manifest.get("files"))
    actual = file_evidence(path)
    _funding_file_manifest(manifest, path.name)
    start_ms = _timestamp_ms(manifest.get("requested_start"), "requested_start")
    end_ms = _timestamp_ms(manifest.get("requested_end"), "requested_end")
    if start_ms >= end_ms:
        raise ValueError("funding manifest has invalid bounds")
    frame = pd.read_parquet(path)
    rows = _rows(frame, start_ms, end_ms)
    _require_manifest_coverage(manifest, frame, start_ms, end_ms)
    _require_raw_parity(
        path.parent,
        manifest,
        normalized_symbol,
        rows,
        start_ms,
        end_ms,
    )
    return HlFundingEvidence(
        symbol=normalized_symbol,
        start_ms=start_ms,
        end_ms=end_ms,
        rows=rows,
        evidence={
            "path": str(path),
            "sha256": actual["sha256"],
            "manifest_path": str(manifest_path),
            "manifest_sha256": file_evidence(manifest_path)["sha256"],
            "requested_start": manifest["requested_start"],
            "requested_end": manifest["requested_end"],
            "complete": True,
            "row_count": len(rows),
        },
    )


def _manifest(path: Path, symbol: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"funding manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("funding manifest must be a JSON object")
    identity = {
        "schema_version": 1,
        "source": "hl_funding_history",
        "source_api": HL_INFO_URL,
        "venue": "hyperliquid",
    }
    if any(value.get(key) != expected for key, expected in identity.items()):
        raise ValueError("funding manifest has an unexpected identity")
    if value.get("complete") is not True or value.get("symbol") != symbol:
        raise ValueError("funding manifest must be complete and match the symbol")
    return value


def _funding_file_manifest(manifest: dict[str, object], name: str) -> dict[str, object]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("funding manifest files must be a mapping")
    value = files.get(name)
    if not isinstance(value, dict):
        raise ValueError("funding manifest is missing normalized evidence")
    return value


def _rows(
    frame: pd.DataFrame, start_ms: int, end_ms: int
) -> tuple[dict[str, object], ...]:
    required = {"timestamp", "event_ts_ms", "funding_rate", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"funding evidence is missing columns: {missing}")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    event_times = pd.to_datetime(frame["event_ts_ms"], unit="ms", utc=True)
    rates = pd.to_numeric(frame["funding_rate"], errors="raise")
    if not timestamps.equals(event_times.dt.floor("h")):
        raise ValueError("funding event timestamps do not match settlement hours")
    if not rates.map(isfinite).all():
        raise ValueError("funding evidence contains non-finite rates")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("funding evidence timestamps must be ordered and unique")
    if ((frame["event_ts_ms"] < start_ms) | (frame["event_ts_ms"] >= end_ms)).any():
        raise ValueError("funding event timestamps fall outside manifest bounds")
    rows = tuple(
        {
            "event_ts_ms": int(row.event_ts_ms),
            "funding_rate": float(row.funding_rate),
            "source": str(row.source),
        }
        for row in frame.itertuples(index=False)
    )
    if any(row["source"] != "hl_funding_history" for row in rows):
        raise ValueError("funding evidence contains a non-official source")
    return rows


def _require_manifest_coverage(
    manifest: dict[str, object],
    frame: pd.DataFrame,
    start_ms: int,
    end_ms: int,
) -> None:
    start = pd.to_datetime(start_ms, unit="ms", utc=True)
    end = pd.to_datetime(end_ms, unit="ms", utc=True)
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    observed = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    counts = {
        "expected_hour_count": len(expected),
        "observed_hour_count": len(observed),
        "missing_hour_count": 0,
    }
    if not observed.equals(expected):
        raise ValueError("funding evidence hourly coverage is incomplete")
    if any(manifest.get(key) != value for key, value in counts.items()):
        raise ValueError("funding manifest hourly coverage counts are inconsistent")
    first = expected.min().isoformat()
    last = expected.max().isoformat()
    if manifest.get("first_observed") != first or manifest.get("last_observed") != last:
        raise ValueError("funding manifest observed bounds are inconsistent")


def _require_raw_parity(
    bundle: Path,
    manifest: dict[str, object],
    symbol: str,
    normalized: tuple[dict[str, object], ...],
    start_ms: int,
    end_ms: int,
) -> None:
    page_count = manifest.get("page_count")
    if not isinstance(page_count, int) or page_count <= 0:
        raise ValueError("funding manifest page_count must be positive")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("funding manifest files must be a mapping")
    expected_pages = [
        f"raw/page-{index:04d}.json.gz" for index in range(1, page_count + 1)
    ]
    actual_pages = sorted(name for name in files if str(name).startswith("raw/"))
    if actual_pages != expected_pages:
        raise ValueError("funding manifest raw pages are not contiguous")
    raw = _raw_rows(bundle, expected_pages, symbol)
    selected = tuple(row for row in raw if start_ms <= int(row["event_ts_ms"]) < end_ms)
    if selected != normalized:
        raise ValueError("funding raw pages do not match normalized evidence")


def _raw_rows(
    bundle: Path, pages: list[str], symbol: str
) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    for relative in pages:
        with open_text_reader(bundle / relative) as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            raise ValueError(f"funding raw page must be a list: {relative}")
        output.extend(_raw_row(row, symbol, relative) for row in value)
    return tuple(sorted(output, key=lambda row: int(row["event_ts_ms"])))


def _raw_row(value: object, symbol: str, page: str) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("coin") != symbol:
        raise ValueError(f"funding raw page has wrong symbol: {page}")
    try:
        event_ts_ms = int(value["time"])
        rate = float(value["fundingRate"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"funding raw page has an invalid row: {page}") from exc
    if not isfinite(rate):
        raise ValueError(f"funding raw page has a non-finite rate: {page}")
    return {
        "event_ts_ms": event_ts_ms,
        "funding_rate": rate,
        "source": "hl_funding_history",
    }


def _timestamp_ms(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"funding manifest {label} must be a timestamp")
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"funding manifest {label} must include a timezone")
    return int(timestamp.timestamp() * 1_000)
