"""Frozen local mark evidence for HIP-3 shadow lifecycle replay."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

import pyarrow.parquet as pq

from hypervector.data.hip3_mark_snapshot_recorder import HIP3_REST_MARK_SOURCE
from hypervector.data.oxa_storage import file_evidence

_EXACT_MARK_SOURCE = "hyperliquid_ws_activeAssetCtx"


class Hip3MarkSourceProtocol(Protocol):
    """Load and revalidate one exact local mark evidence set."""

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        """Return bounded mark rows and immutable source evidence."""

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        """Fail if any consumed immutable mark part changed."""


class HyperliquidL2SourceProtocol(Protocol):
    """Load and revalidate one exact local L2 evidence set."""

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        """Return bounded L2 rows and immutable source evidence."""

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        """Fail if any consumed immutable L2 part changed."""


class FrozenHip3MarkArchive:
    """Read an exact set of immutable local activeAssetCtx Parquet parts."""

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        """Capture and read files intersecting one explicit receipt-time window."""
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("HIP-3 mark archive window must be positive")
        paths = _mark_parts(data_root, symbol, start_ms, end_ms)
        if not paths:
            raise FileNotFoundError(f"HIP-3 mark archive has no parts for {symbol}")
        files = tuple(_part_evidence(path) for path in paths)
        rows, excluded = _read_rows(paths, start_ms, end_ms)
        return rows, {
            "rows": len(rows),
            "excluded_supplemental_rows": excluded,
            "files": list(files),
        }

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        """Rehash every consumed immutable Parquet part."""
        _require_files_unchanged(evidence, "mark")


class FrozenHyperliquidL2Archive:
    """Read an exact set of immutable local L2 Parquet parts."""

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        """Capture and read books intersecting one receipt-time window."""
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("Hyperliquid L2 archive window must be positive")
        paths = _l2_parts(data_root, symbol, start_ms, end_ms)
        if not paths:
            raise FileNotFoundError(f"Hyperliquid L2 archive has no parts for {symbol}")
        files = tuple(_part_evidence(path) for path in paths)
        rows = _read_l2_rows(paths, symbol, start_ms, end_ms)
        return rows, {"rows": len(rows), "files": list(files)}

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        """Rehash every consumed immutable L2 Parquet part."""
        _require_files_unchanged(evidence, "L2")


def _require_files_unchanged(evidence: Mapping[str, object], label: str) -> None:
    raw_files = evidence.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError(f"Hyperliquid {label} evidence has no immutable files")
    raw_files = evidence.get("files")
    for raw in raw_files:
        row = _mapping(raw, f"{label} file evidence")
        path = Path(_text(row.get("path"), f"{label} file path"))
        expected = {"sha256": row.get("sha256"), "bytes": row.get("bytes")}
        if file_evidence(path) != expected:
            raise ValueError(
                f"Hyperliquid {label} archive changed during replay: {path}"
            )


def _mark_parts(
    data_root: Path, symbol: str, start_ms: int, end_ms: int
) -> tuple[Path, ...]:
    root = data_root / "cache/events/hyperliquid" / symbol
    paths: list[Path] = []
    for day in _utc_days(start_ms, end_ms):
        paths.extend(
            sorted((root / day / "asset_context.parquet").glob("part-*.parquet"))
        )
    return tuple(paths)


def _l2_parts(
    data_root: Path, symbol: str, start_ms: int, end_ms: int
) -> tuple[Path, ...]:
    root = data_root / "cache/events/hyperliquid" / symbol
    paths: list[Path] = []
    for day in _utc_days(start_ms, end_ms):
        paths.extend(sorted((root / day / "l2.parquet").glob("part-*.parquet")))
    return tuple(paths)


def _read_rows(
    paths: tuple[Path, ...], start_ms: int, end_ms: int
) -> tuple[tuple[dict[str, object], ...], int]:
    filters = [
        ("received_ts_ns", ">=", start_ms * 1_000_000),
        ("received_ts_ns", "<=", end_ms * 1_000_000),
    ]
    rows: list[dict[str, object]] = []
    columns = ["symbol", "observed_ts_ms", "received_ts_ns", "mark_price", "source"]
    for path in paths:
        rows.extend(
            cast(
                list[dict[str, object]],
                pq.read_table(path, columns=columns, filters=filters).to_pylist(),
            )
        )
    sources = {str(row["source"]) for row in rows}
    invalid = sources.difference({_EXACT_MARK_SOURCE, HIP3_REST_MARK_SOURCE})
    if invalid:
        raise ValueError(
            f"HIP-3 mark archive contains unknown sources: {sorted(invalid)}"
        )
    exact = tuple(row for row in rows if row["source"] == _EXACT_MARK_SOURCE)
    ordered = tuple(
        sorted(exact, key=lambda row: int(cast(int, row["received_ts_ns"])))
    )
    return ordered, len(rows) - len(exact)


def _read_l2_rows(
    paths: tuple[Path, ...], symbol: str, start_ms: int, end_ms: int
) -> tuple[dict[str, object], ...]:
    filters = [
        ("received_ts_ns", ">=", start_ms * 1_000_000),
        ("received_ts_ns", "<=", end_ms * 1_000_000),
    ]
    columns = [
        "symbol",
        "exchange_ts_ms",
        "received_ts_ns",
        "bids",
        "asks",
        "source",
    ]
    rows: list[dict[str, object]] = []
    for path in paths:
        rows.extend(
            cast(
                list[dict[str, object]],
                pq.read_table(path, columns=columns, filters=filters).to_pylist(),
            )
        )
    if any(
        row.get("symbol") != symbol or row.get("source") != "hyperliquid_ws_l2Book"
        for row in rows
    ):
        raise ValueError("Hyperliquid L2 archive identity differs")
    ordered = tuple(sorted(rows, key=lambda row: int(cast(int, row["received_ts_ns"]))))
    timestamps = tuple(int(cast(int, row["received_ts_ns"])) for row in ordered)
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Hyperliquid L2 receipt timestamps are not unique")
    return ordered


def _part_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _utc_days(start_ms: int, end_ms: int) -> tuple[str, ...]:
    day = datetime.fromtimestamp(start_ms / 1_000, tz=UTC).date()
    last = datetime.fromtimestamp(end_ms / 1_000, tz=UTC).date()
    result: list[str] = []
    while day <= last:
        result.append(day.isoformat())
        day += timedelta(days=1)
    return tuple(result)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value
