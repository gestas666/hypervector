"""Exact archive mark overlays for report-only HIP-3 lifecycle replays."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import cast

import pandas as pd

from hypervector.data.oxa_price_archive import (
    OxaPriceArchiveConfig,
    load_verified_price_archive,
)
from hypervector.data.oxa_prices import OxaPriceRequest, price_output_directory
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_prospective_path_audit import hip3_bar_path_quality
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHip3MarkArchive,
    Hip3MarkSourceProtocol,
)

HIP3_ARCHIVE_REPAIR_MARK_SOURCE = "0xarchive_exact_exchange_mark_repair"


def configured_archive_mark_source(
    audit_path: Path | None,
    data_root: Path,
    symbol: str,
    maximum_gap_ms: int,
    base: Hip3MarkSourceProtocol | None,
) -> Hip3MarkSourceProtocol | None:
    """Build an audit-bounded overlay, or preserve the caller's base source."""
    if audit_path is None:
        return base
    report = _json_object(audit_path, "prospective path audit")
    windows = _audit_windows(report, symbol)
    start = _hour_floor(min(window[0] for window in windows))
    end = _hour_ceiling(max(window[1] for window in windows))
    archive = OxaPriceArchiveConfig(
        symbol,
        start,
        end,
        data_root,
        chunk=timedelta(hours=1),
        maximum_gap=None,
        market_family="hip3",
    )
    return ArchiveRepairingHip3MarkSource(
        audit_path, archive, maximum_gap_ms, base=base
    )


class ArchiveRepairingHip3MarkSource:
    """Overlay audit-scoped exact archive marks on a frozen live mark prefix."""

    def __init__(
        self,
        audit_path: Path,
        archive: OxaPriceArchiveConfig,
        maximum_gap_ms: int,
        *,
        base: Hip3MarkSourceProtocol | None = None,
    ) -> None:
        if isinstance(maximum_gap_ms, bool) or maximum_gap_ms <= 0:
            raise ValueError("archive mark repair maximum gap must be positive")
        self._audit_path = audit_path
        self._archive = archive
        self._maximum_gap_ms = maximum_gap_ms
        self._base = base or FrozenHip3MarkArchive()

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        """Return live rows plus exact archive rows only inside declared gaps."""
        self._require_identity(data_root, symbol, start_ms, end_ms)
        base_rows, base_evidence = self._base.load(
            data_root=data_root, symbol=symbol, start_ms=start_ms, end_ms=end_ms
        )
        audit = _json_object(self._audit_path, "prospective path audit")
        windows = _repair_windows(audit, symbol, self._archive, self._maximum_gap_ms)
        archive = load_verified_price_archive(self._archive)
        if archive.missing_mark_row_count or archive.empty_partition_count:
            raise ValueError("archive mark repair contains missing mark evidence")
        candidates = _archive_rows(archive.frame, windows, symbol)
        repair_rows, repaired_windows = _resolved_archive_rows(
            candidates, windows, self._maximum_gap_ms
        )
        if not repaired_windows:
            raise ValueError("archive mark repair has no technically complete windows")
        merged = _merge_rows(base_rows, repair_rows)
        files = _archive_files(self._archive)
        added = sum(
            row.get("source") == HIP3_ARCHIVE_REPAIR_MARK_SOURCE for row in merged
        )
        evidence = {
            "base": base_evidence,
            "repair_audit": _path_evidence(self._audit_path),
            "archive_files": list(files),
            "archive_repair_rows": added,
            "archive_repaired_windows": repaired_windows,
            "archive_unresolved_windows": len(windows) - repaired_windows,
            "repair_windows": [list(window) for window in windows],
        }
        return merged, evidence

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        """Rehash the base source, audit, and every archive partition."""
        base = _mapping(evidence.get("base"), "base mark evidence")
        self._base.require_unchanged(base)
        expected_audit = _mapping(evidence.get("repair_audit"), "repair audit")
        if _path_evidence(self._audit_path) != dict(expected_audit):
            raise ValueError("archive mark repair audit changed")
        expected_files = _evidence_rows(evidence.get("archive_files"))
        if _archive_files(self._archive) != expected_files:
            raise ValueError("archive mark repair files changed")

    def _require_identity(
        self, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> None:
        if data_root.resolve() != self._archive.data_root.resolve():
            raise ValueError("archive mark repair data root is inconsistent")
        if symbol != self._archive.symbol:
            raise ValueError("archive mark repair symbol is inconsistent")
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("archive mark repair replay bounds are invalid")


def _repair_windows(
    report: Mapping[str, object],
    symbol: str,
    archive: OxaPriceArchiveConfig,
    maximum_gap_ms: int,
) -> tuple[tuple[int, int], ...]:
    windows = _audit_windows(report, symbol)
    lower = int(archive.start.timestamp() * 1_000)
    upper = int(archive.end.timestamp() * 1_000)
    if any(start < lower or end > upper for start, end in windows):
        raise ValueError(
            "archive mark repair does not cover every incomplete mark window"
        )
    if maximum_gap_ms > int(archive.chunk.total_seconds() * 1_000):
        raise ValueError("archive mark repair threshold exceeds its partition cadence")
    return windows


def _audit_windows(
    report: Mapping[str, object], symbol: str
) -> tuple[tuple[int, int], ...]:
    if report.get("schema_version") != "hip3_prospective_path_audit_v1":
        raise ValueError("archive mark repair audit schema is invalid")
    contract = _mapping(report.get("contract"), "audit contract")
    source = _mapping(report.get("source"), "audit source")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("archive mark repair audit authority is invalid")
    if source.get("symbol") != symbol:
        raise ValueError("archive mark repair audit symbol is inconsistent")
    rows = _diagnostic_rows(report)
    windows = tuple(
        _incomplete_mark_window(row) for row in rows if not _mark_complete(row)
    )
    if not windows:
        raise ValueError("archive mark repair audit has no incomplete mark windows")
    return windows


def _archive_rows(
    frame: pd.DataFrame,
    windows: tuple[tuple[int, int], ...],
    symbol: str,
) -> tuple[dict[str, object], ...]:
    selected = frame.loc[frame["mark_price"].notna()].copy()
    keep = pd.Series(False, index=selected.index)
    for start, end in windows:
        keep |= selected["ts_ms"].between(start, end, inclusive="both")
    output = []
    for row in selected.loc[keep].itertuples(index=False):
        timestamp = int(row.ts_ms)
        output.append(
            {
                "symbol": symbol,
                "observed_ts_ms": timestamp,
                "received_ts_ns": timestamp * 1_000_000,
                "mark_price": float(row.mark_price),
                "source": HIP3_ARCHIVE_REPAIR_MARK_SOURCE,
            }
        )
    return tuple(output)


def _resolved_archive_rows(
    rows: tuple[dict[str, object], ...],
    windows: tuple[tuple[int, int], ...],
    maximum_gap_ms: int,
) -> tuple[tuple[dict[str, object], ...], int]:
    timestamps = [int(row["observed_ts_ms"]) for row in rows]
    resolved: list[tuple[int, int]] = []
    for start, end in windows:
        quality = hip3_bar_path_quality(
            timestamps, start_ms=start, end_ms=end, maximum_gap_ms=maximum_gap_ms
        )
        if quality.get("complete") is True:
            resolved.append((start, end))
    selected = tuple(
        row
        for row in rows
        if any(start <= int(row["observed_ts_ms"]) <= end for start, end in resolved)
    )
    return selected, len(resolved)


def _merge_rows(
    base: tuple[dict[str, object], ...], repair: tuple[dict[str, object], ...]
) -> tuple[dict[str, object], ...]:
    base_times = {int(row["observed_ts_ms"]) for row in base}
    additions = [row for row in repair if int(row["observed_ts_ms"]) not in base_times]
    return tuple(
        sorted((*base, *additions), key=lambda row: int(row["received_ts_ns"]))
    )


def _archive_files(config: OxaPriceArchiveConfig) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        directory = price_output_directory(
            config.data_root,
            OxaPriceRequest(
                config.symbol, start, end, market_family=config.market_family
            ),
        )
        output.extend(
            _path_evidence(directory / name)
            for name in ("manifest.json", "prices.parquet")
        )
        start = end
    return tuple(output)


def _diagnostic_rows(report: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = report.get("bar_diagnostics")
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(row, dict) for row in raw)
    ):
        raise ValueError("archive mark repair audit diagnostics are invalid")
    return tuple(cast(list[dict[str, object]], raw))


def _mark_complete(row: Mapping[str, object]) -> bool:
    value = _mapping(row.get("mark"), "mark diagnostic").get("complete")
    if not isinstance(value, bool):
        raise ValueError("archive mark repair mark completeness must be boolean")
    return value


def _incomplete_mark_window(row: Mapping[str, object]) -> tuple[int, int]:
    start = _integer(row.get("bar_open_ms"), "bar open")
    end = _integer(row.get("bar_close_ms"), "bar close")
    if end - start != 15 * 60_000:
        raise ValueError("archive mark repair requires exact 15m diagnostics")
    return start, end


def _evidence_rows(value: object) -> tuple[dict[str, object], ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(row, dict) for row in value)
    ):
        raise ValueError("archive mark repair file evidence is invalid")
    return tuple(cast(list[dict[str, object]], value))


def _json_object(path: Path, label: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"archive mark repair {label} must be a nonnegative integer")
    return value


def _hour_floor(timestamp_ms: int) -> datetime:
    value = datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
    return value.replace(minute=0, second=0, microsecond=0)


def _hour_ceiling(timestamp_ms: int) -> datetime:
    value = datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
    floor = value.replace(minute=0, second=0, microsecond=0)
    return floor if value == floor else floor + timedelta(hours=1)
