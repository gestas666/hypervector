"""Targeted causal 0xArchive order-book windows for labeled entries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_backfill import OxaBackfillTask
from hypervector.data.oxa_history import OxaBookRequest, output_directory
from hypervector.data.oxa_storage import open_text_reader, verify_file_evidence

_REQUIRED_COLUMNS = ("side", "signal_time_utc", "entry_time_utc")


@dataclass(frozen=True)
class OxaSignalWindow:
    """One immutable labeled entry and its causal/execution L2 bounds."""

    window_id: str
    side: str
    signal_time: datetime
    entry_time: datetime
    start: datetime
    end: datetime


@dataclass(frozen=True)
class OxaSignalWindowAuditRow:
    """Coverage and timing evidence for one requested signal window."""

    window_id: str
    side: str
    signal_time_utc: str
    entry_time_utc: str
    bundle_path: str
    status: str
    manifest_complete: bool
    row_count: int
    pre_entry_rows: int
    post_entry_rows: int
    last_pre_entry_age_ms: int | None
    first_post_entry_delay_ms: int | None
    causal_covered: bool
    execution_covered: bool


@dataclass(frozen=True)
class OxaSignalWindowAudit:
    """Aggregate coverage proof for a complete targeted signal set."""

    complete: bool
    expected_signals: int
    bundles_complete: int
    causal_covered: int
    execution_covered: int
    total_rows: int
    rows: tuple[OxaSignalWindowAuditRow, ...]

    def as_payload(self) -> dict[str, object]:
        """Return deterministic JSON-compatible audit evidence."""
        return {
            "schema_version": 1,
            "mode": "oxa_signal_window_l2_coverage",
            "complete": self.complete,
            "summary": {
                "expected_signals": self.expected_signals,
                "bundles_complete": self.bundles_complete,
                "causal_covered": self.causal_covered,
                "execution_covered": self.execution_covered,
                "total_rows": self.total_rows,
            },
            "rows": [asdict(row) for row in self.rows],
        }

    def index_frame(self) -> pd.DataFrame:
        """Return the per-signal join index without copying L2 payloads."""
        return pd.DataFrame([asdict(row) for row in self.rows])


def load_signal_windows(
    feature_path: Path,
    *,
    pre_seconds: int,
    post_seconds: int,
) -> tuple[OxaSignalWindow, ...]:
    """Load only identity columns from a frozen feature Parquet file."""
    if not feature_path.is_file():
        raise FileNotFoundError(f"signal feature file not found: {feature_path}")
    frame = pd.read_parquet(feature_path, columns=list(_REQUIRED_COLUMNS))
    return build_signal_windows(frame, pre_seconds, post_seconds)


def build_signal_windows(
    frame: pd.DataFrame,
    pre_seconds: int,
    post_seconds: int,
) -> tuple[OxaSignalWindow, ...]:
    """Build exact non-overlapping entry windows from causal timestamps."""
    _validate_frame(frame, pre_seconds, post_seconds)
    signals = pd.to_datetime(frame["signal_time_utc"], utc=True, errors="raise")
    entries = pd.to_datetime(frame["entry_time_utc"], utc=True, errors="raise")
    if entries.duplicated().any():
        raise ValueError("signal features contain duplicate entry times")
    windows = tuple(
        _build_window(side, signal, entry, pre_seconds, post_seconds)
        for side, signal, entry in zip(frame["side"], signals, entries, strict=True)
    )
    return tuple(sorted(windows, key=lambda value: value.entry_time))


def tasks_for_signal_windows(
    windows: tuple[OxaSignalWindow, ...],
) -> tuple[OxaBackfillTask, ...]:
    """Map exact signal windows to book-only resumable tasks."""
    if not windows:
        raise ValueError("signal windows cannot be empty")
    return tuple(OxaBackfillTask("book", value.start, value.end) for value in windows)


def audit_signal_windows(
    *,
    data_root: Path,
    symbol: str,
    depth: int,
    windows: tuple[OxaSignalWindow, ...],
    maximum_pre_entry_age_ms: int,
    maximum_post_entry_delay_ms: int,
) -> OxaSignalWindowAudit:
    """Verify bundle identity, hashes, rows, and entry-boundary coverage."""
    _validate_audit_bounds(
        windows, maximum_pre_entry_age_ms, maximum_post_entry_delay_ms
    )
    rows = tuple(
        _audit_window(
            data_root,
            symbol,
            depth,
            window,
            maximum_pre_entry_age_ms,
            maximum_post_entry_delay_ms,
        )
        for window in windows
    )
    bundles = sum(row.manifest_complete for row in rows)
    causal = sum(row.causal_covered for row in rows)
    execution = sum(row.execution_covered for row in rows)
    expected = len(rows)
    return OxaSignalWindowAudit(
        complete=bundles == causal == execution == expected,
        expected_signals=expected,
        bundles_complete=bundles,
        causal_covered=causal,
        execution_covered=execution,
        total_rows=sum(row.row_count for row in rows),
        rows=rows,
    )


def _validate_frame(frame: pd.DataFrame, pre_seconds: int, post_seconds: int) -> None:
    missing = sorted(set(_REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"signal features are missing columns: {','.join(missing)}")
    if frame.empty:
        raise ValueError("signal features cannot be empty")
    if pre_seconds < 1 or post_seconds < 1:
        raise ValueError("pre and post signal windows must be positive")
    sides = set(frame["side"].astype(str))
    if not sides.issubset({"long", "short"}):
        raise ValueError("signal side must be long or short")


def _build_window(
    side: object,
    signal: pd.Timestamp,
    entry: pd.Timestamp,
    pre_seconds: int,
    post_seconds: int,
) -> OxaSignalWindow:
    signal_time = signal.to_pydatetime().astimezone(UTC)
    entry_time = entry.to_pydatetime().astimezone(UTC)
    if signal_time >= entry_time:
        raise ValueError("signal time must be before entry time")
    start = entry_time - timedelta(seconds=pre_seconds)
    end = entry_time + timedelta(seconds=post_seconds)
    identity = f"{side}|{signal_time.isoformat()}|{entry_time.isoformat()}"
    return OxaSignalWindow(
        window_id=hashlib.sha256(identity.encode()).hexdigest(),
        side=str(side),
        signal_time=signal_time,
        entry_time=entry_time,
        start=start,
        end=end,
    )


def _validate_audit_bounds(
    windows: tuple[OxaSignalWindow, ...],
    maximum_pre_entry_age_ms: int,
    maximum_post_entry_delay_ms: int,
) -> None:
    if not windows:
        raise ValueError("signal windows cannot be empty")
    if maximum_pre_entry_age_ms < 0 or maximum_post_entry_delay_ms < 0:
        raise ValueError("entry snapshot timing bounds cannot be negative")


def _audit_window(
    data_root: Path,
    symbol: str,
    depth: int,
    window: OxaSignalWindow,
    maximum_pre_age_ms: int,
    maximum_post_delay_ms: int,
) -> OxaSignalWindowAuditRow:
    request = OxaBookRequest(symbol, window.start, window.end, depth)
    directory = output_directory(data_root, request)
    try:
        manifest = _verified_manifest(directory, request)
        timestamps = _book_timestamps(directory / "books.jsonl.gz")
        expected_rows = manifest.get("row_count")
        if not isinstance(expected_rows, int) or expected_rows != len(timestamps):
            raise ValueError("manifest row count differs from replay rows")
        return _timing_row(
            window,
            directory,
            timestamps,
            maximum_pre_age_ms,
            maximum_post_delay_ms,
        )
    except (OSError, ValueError) as exc:
        return _invalid_row(window, directory, str(exc))


def _verified_manifest(directory: Path, request: OxaBookRequest) -> dict[str, object]:
    path = directory / "manifest.json"
    if not path.is_file():
        raise ValueError("bundle manifest is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    identity = (
        payload.get("source") == "0xarchive_hyperliquid_native_l2"
        and payload.get("symbol") == request.symbol
        and payload.get("requested_start") == request.start.isoformat()
        and payload.get("requested_end") == request.end.isoformat()
        and payload.get("requested_depth") == request.depth
    )
    if not identity:
        raise ValueError("bundle manifest identity mismatch")
    if (
        payload.get("complete") is not True
        or payload.get("continuation_cursor") is not None
    ):
        raise ValueError("bundle manifest is incomplete")
    verify_file_evidence(directory, payload.get("files"))
    return payload


def _book_timestamps(path: Path) -> tuple[int, ...]:
    values: list[int] = []
    with open_text_reader(path) as handle:
        for line in handle:
            payload = json.loads(line)
            timestamp = payload.get("ts_exchange_ms")
            if not isinstance(timestamp, int):
                raise ValueError("book row has no integer exchange timestamp")
            values.append(timestamp)
    if values != sorted(set(values)):
        raise ValueError("book timestamps are duplicated or out of order")
    return tuple(values)


def _timing_row(
    window: OxaSignalWindow,
    directory: Path,
    timestamps: tuple[int, ...],
    maximum_pre_age_ms: int,
    maximum_post_delay_ms: int,
) -> OxaSignalWindowAuditRow:
    entry_ms = int(window.entry_time.timestamp() * 1_000)
    before = tuple(value for value in timestamps if value < entry_ms)
    after = tuple(value for value in timestamps if value >= entry_ms)
    pre_age = entry_ms - before[-1] if before else None
    post_delay = after[0] - entry_ms if after else None
    causal = pre_age is not None and pre_age <= maximum_pre_age_ms
    execution = post_delay is not None and post_delay <= maximum_post_delay_ms
    status = _coverage_status(before, after, causal, execution)
    return OxaSignalWindowAuditRow(
        window.window_id,
        window.side,
        window.signal_time.isoformat(),
        window.entry_time.isoformat(),
        str(directory),
        status,
        True,
        len(timestamps),
        len(before),
        len(after),
        pre_age,
        post_delay,
        causal,
        execution,
    )


def _coverage_status(
    before: tuple[int, ...],
    after: tuple[int, ...],
    causal: bool,
    execution: bool,
) -> str:
    if not before:
        return "missing_pre_entry_snapshot"
    if not causal:
        return "stale_pre_entry_snapshot"
    if not after:
        return "missing_post_entry_snapshot"
    if not execution:
        return "delayed_post_entry_snapshot"
    return "covered"


def _invalid_row(
    window: OxaSignalWindow,
    directory: Path,
    issue: str,
) -> OxaSignalWindowAuditRow:
    return OxaSignalWindowAuditRow(
        window.window_id,
        window.side,
        window.signal_time.isoformat(),
        window.entry_time.isoformat(),
        str(directory),
        f"invalid_bundle: {issue}",
        False,
        0,
        0,
        0,
        None,
        None,
        False,
        False,
    )
