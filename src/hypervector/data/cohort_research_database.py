"""Incremental append-only ingestion for private live cohort journals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import pyarrow as pa

from hypervector.data.cohort_research_sql import COHORT_LIVE_SCHEMA_SQL
from hypervector.data.reporting_duckdb import connect_reporting_database

_EVENT_COLUMNS = (
    "event_id",
    "source_path",
    "ledger_symbol",
    "schema_version",
    "sequence",
    "event_type",
    "observed_at_utc",
    "execution_mode",
    "effective_mode",
    "live_armed",
    "execution_authority",
    "profile_id",
    "profile_fingerprint",
    "run_fingerprint",
    "run_id",
    "payload",
)
_INSERT_SQL = """
INSERT OR IGNORE INTO cohort_live_events
SELECT
    event_id, source_path, ledger_symbol, schema_version, sequence, event_type,
    observed_at_utc, execution_mode, effective_mode, live_armed,
    execution_authority, profile_id, profile_fingerprint, run_fingerprint,
    run_id, CAST(payload AS JSON)
FROM cohort_import_batch
"""
_SOURCE_SQL = """
INSERT INTO cohort_live_sources (
    source_path, ledger_symbol, imported_bytes, prefix_sha256, imported_rows
) VALUES (?, ?, ?, ?, ?)
ON CONFLICT (source_path) DO UPDATE SET
    ledger_symbol = excluded.ledger_symbol,
    imported_bytes = excluded.imported_bytes,
    prefix_sha256 = excluded.prefix_sha256,
    imported_rows = excluded.imported_rows,
    updated_at_utc = now()
"""
_HASH_CHUNK_BYTES = 1024 * 1024
_TAIL_SCAN_BYTES = 64 * 1024


@dataclass(frozen=True)
class CohortLedgerIngestReport:
    """Counts from one atomic incremental cohort-journal import."""

    source_files: int
    updated_files: int
    scanned_events: int
    imported_events: int
    skipped_events: int
    ignored_observe_events: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _SourceState:
    imported_bytes: int
    prefix_sha256: str
    imported_rows: int


@dataclass(frozen=True)
class _SourceIncrement:
    source_path: str
    ledger_symbol: str
    processed_bytes: int
    prefix_sha256: str
    prior_rows: int
    scanned_events: int
    ignored_observe_events: int
    rows: tuple[tuple[object, ...], ...]


def ingest_cohort_live_ledger(
    database_path: Path,
    ledger_root: Path,
) -> CohortLedgerIngestReport:
    """Atomically append every complete live ledger line to DuckDB."""
    files = _ledger_files(ledger_root)
    with connect_reporting_database(database_path) as connection:
        connection.execute(COHORT_LIVE_SCHEMA_SQL)
        increments = tuple(_source_increment(connection, path) for path in files)
        before = _event_count(connection)
        _commit_increments(connection, increments)
        imported = _event_count(connection) - before
    scanned = sum(increment.scanned_events for increment in increments)
    return CohortLedgerIngestReport(
        source_files=len(files),
        updated_files=sum(bool(item.scanned_events) for item in increments),
        scanned_events=scanned,
        imported_events=imported,
        skipped_events=scanned - imported,
        ignored_observe_events=sum(
            increment.ignored_observe_events for increment in increments
        ),
    )


def cohort_live_summary(database_path: Path) -> dict[str, int]:
    """Return durable source, event, fill, and run counts."""
    with connect_reporting_database(database_path) as connection:
        connection.execute(COHORT_LIVE_SCHEMA_SQL)
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM cohort_live_sources),
                (SELECT count(*) FROM cohort_live_events),
                (SELECT count(*) FROM cohort_live_fills),
                (SELECT count(*) FROM cohort_live_closed_fills),
                (SELECT count(*) FROM cohort_live_attributed_fills),
                (SELECT count(*) FROM cohort_live_close_orders),
                (SELECT count(DISTINCT run_id) FROM cohort_live_events)
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("cohort live summary query returned no row")
    labels = (
        "source_files",
        "events",
        "fills",
        "closed_fills",
        "attributed_fills",
        "close_orders",
        "runs",
    )
    return dict(zip(labels, map(int, row), strict=True))


def cohort_live_freshness(database_path: Path) -> dict[str, object]:
    """Report filesystem-to-DuckDB lag for every imported cohort ledger."""
    with connect_reporting_database(database_path) as connection:
        connection.execute(COHORT_LIVE_SCHEMA_SQL)
        rows = connection.execute(
            """
            SELECT source.source_path, source.ledger_symbol,
                   source.imported_bytes, source.updated_at_utc,
                   max(event.observed_at_utc) AS latest_event_at_utc
            FROM cohort_live_sources AS source
            LEFT JOIN cohort_live_events AS event USING (source_path)
            GROUP BY ALL ORDER BY source.ledger_symbol, source.source_path
            """
        ).fetchall()
    sources = tuple(_source_freshness(row) for row in rows)
    counts = _freshness_counts(sources)
    return {
        "state": _freshness_state(counts),
        **counts,
        "latest_imported_event_at_utc": _latest_timestamp(
            sources, "latest_imported_event_at_utc"
        ),
        "latest_source_update_at_utc": _latest_timestamp(
            sources, "source_updated_at_utc"
        ),
        "sources": list(sources),
    }


def _source_freshness(row: tuple[object, ...]) -> dict[str, object]:
    source = Path(str(row[0]))
    imported_bytes = int(row[2])
    file_bytes = source.stat().st_size if source.is_file() else None
    delta = None if file_bytes is None else file_bytes - imported_bytes
    state = _source_freshness_state(delta)
    return {
        "source_path": str(source),
        "ledger_symbol": str(row[1]),
        "state": state,
        "imported_bytes": imported_bytes,
        "file_bytes": file_bytes,
        "pending_bytes": max(delta, 0) if delta is not None else None,
        "source_updated_at_utc": _timestamp_text(row[3]),
        "latest_imported_event_at_utc": _timestamp_text(row[4]),
    }


def _source_freshness_state(delta: int | None) -> str:
    if delta is None:
        return "source_missing"
    if delta < 0:
        return "source_truncated"
    return "synchronized" if delta == 0 else "pending_import"


def _freshness_counts(sources: tuple[dict[str, object], ...]) -> dict[str, int]:
    states = tuple(str(source["state"]) for source in sources)
    return {
        "source_files": len(sources),
        "synchronized_files": states.count("synchronized"),
        "pending_files": states.count("pending_import"),
        "missing_files": states.count("source_missing"),
        "truncated_files": states.count("source_truncated"),
        "pending_bytes": sum(int(source["pending_bytes"] or 0) for source in sources),
    }


def _freshness_state(counts: Mapping[str, int]) -> str:
    if counts["missing_files"] or counts["truncated_files"]:
        return "source_integrity_error"
    return "pending_import" if counts["pending_files"] else "synchronized"


def _latest_timestamp(sources: tuple[dict[str, object], ...], field: str) -> str | None:
    values = [str(source[field]) for source in sources if source[field] is not None]
    return max(values, default=None)


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("cohort freshness timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _ledger_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FileNotFoundError(f"cohort ledger root is missing: {root}")
    files = tuple(sorted(root.glob("*.jsonl")))
    if not files:
        raise FileNotFoundError(f"cohort ledger root has no JSONL files: {root}")
    return files


def _source_increment(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> _SourceIncrement:
    source = str(path.resolve())
    state = _source_state(connection, source)
    complete_size = _complete_prefix_size(path)
    prior_bytes = 0 if state is None else state.imported_bytes
    if prior_bytes > complete_size:
        raise ValueError(f"cohort ledger was truncated: {path}")
    if state is not None and _sha256_prefix(path, prior_bytes) != state.prefix_sha256:
        raise ValueError(f"cohort ledger append-only prefix changed: {path}")
    new_data = _read_range(path, prior_bytes, complete_size)
    ledger_symbol = _ledger_symbol(path)
    rows, ignored_observe_events = _parse_lines(source, ledger_symbol, new_data)
    _validate_new_identities(connection, source, rows)
    return _SourceIncrement(
        source,
        ledger_symbol,
        complete_size,
        _sha256_prefix(path, complete_size),
        0 if state is None else state.imported_rows,
        len(new_data.splitlines()),
        ignored_observe_events,
        rows,
    )


def _complete_prefix_size(path: Path) -> int:
    """Return the byte boundary after the latest complete JSONL record."""
    size = path.stat().st_size
    if size == 0:
        return 0
    with path.open("rb") as handle:
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return size
        cursor = size
        while cursor > 0:
            start = max(0, cursor - _TAIL_SCAN_BYTES)
            handle.seek(start)
            block = handle.read(cursor - start)
            boundary = block.rfind(b"\n")
            if boundary >= 0:
                return start + boundary + 1
            cursor = start
    return 0


def _read_range(path: Path, start: int, end: int) -> bytes:
    """Read one validated byte range without retaining the imported prefix."""
    if start < 0 or end < start:
        raise ValueError("cohort ledger byte range is invalid")
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read(end - start)
    if len(data) != end - start:
        raise OSError(f"cohort ledger changed while reading: {path}")
    return data


def _sha256_prefix(path: Path, length: int) -> str:
    """Hash an exact file prefix in bounded chunks."""
    digest = hashlib.sha256()
    remaining = length
    with path.open("rb") as handle:
        while remaining:
            block = handle.read(min(remaining, _HASH_CHUNK_BYTES))
            if not block:
                raise OSError(f"cohort ledger changed while hashing: {path}")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _parse_lines(
    source: str,
    ledger_symbol: str,
    data: bytes,
) -> tuple[tuple[tuple[object, ...], ...], int]:
    rows: list[tuple[object, ...]] = []
    identities: set[tuple[str, int]] = set()
    ignored_observe_events = 0
    for raw in data.splitlines():
        value = json.loads(raw)
        if _execution_incapable_observe(value):
            ignored_observe_events += 1
            continue
        row = _event_row(source, ledger_symbol, raw, value)
        identity = (str(row[14]), int(row[4]))
        if identity in identities:
            raise ValueError(f"duplicate cohort run sequence in {source}: {identity}")
        identities.add(identity)
        rows.append(row)
    return tuple(rows), ignored_observe_events


def _execution_incapable_observe(value: object) -> bool:
    """Identify explicitly unarmed observe telemetry for exclusion from live data."""
    row = _mapping(value, "cohort ledger row")
    if row.get("execution_mode") != "observe":
        return False
    if row.get("live_armed") is not False:
        raise ValueError("observe cohort row must be explicitly unarmed")
    if row.get("execution_authority") != "none":
        raise ValueError("observe cohort row must have no execution authority")
    return True


def _event_row(
    source: str,
    ledger_symbol: str,
    raw: bytes,
    value: object,
) -> tuple[object, ...]:
    row = _mapping(value, "cohort ledger row")
    if row.get("execution_mode") != "live":
        raise ValueError("cohort execution_mode must be live")
    sequence = _nonnegative_integer(row.get("sequence"), "cohort sequence")
    timestamp = _timestamp(_text(row, "observed_at_utc"))
    payload = _mapping(row.get("payload"), "cohort payload")
    event_id = hashlib.sha256(source.encode() + b"\0" + raw).hexdigest()
    return (
        event_id,
        source,
        ledger_symbol,
        _nonnegative_integer(row.get("schema_version"), "cohort schema version"),
        sequence,
        _text(row, "event_type"),
        timestamp,
        "live",
        _text(row, "effective_mode"),
        _boolean(row.get("live_armed"), "live_armed"),
        _text(row, "execution_authority"),
        _text(row, "profile_id"),
        _text(row, "profile_fingerprint"),
        _text(row, "run_fingerprint"),
        _text(row, "run_id"),
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )


def _validate_new_identities(
    connection: duckdb.DuckDBPyConnection,
    source: str,
    rows: tuple[tuple[object, ...], ...],
) -> None:
    for row in rows:
        existing = connection.execute(
            """
            SELECT event_id FROM cohort_live_events
            WHERE source_path = ? AND run_id = ? AND sequence = ?
            """,
            [source, row[14], row[4]],
        ).fetchone()
        if existing is not None and existing[0] != row[0]:
            raise ValueError(f"conflicting cohort run sequence in {source}")


def _commit_increments(
    connection: duckdb.DuckDBPyConnection,
    increments: tuple[_SourceIncrement, ...],
) -> None:
    connection.execute("BEGIN TRANSACTION")
    try:
        for increment in increments:
            _reconcile_ledger_symbol(connection, increment)
            if increment.rows:
                _insert_event_batch(connection, increment.rows)
            connection.execute(
                _SOURCE_SQL,
                [
                    increment.source_path,
                    increment.ledger_symbol,
                    increment.processed_bytes,
                    increment.prefix_sha256,
                    increment.prior_rows + len(increment.rows),
                ],
            )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _reconcile_ledger_symbol(
    connection: duckdb.DuckDBPyConnection,
    increment: _SourceIncrement,
) -> None:
    connection.execute(
        """
        UPDATE cohort_live_events
        SET ledger_symbol = ?
        WHERE source_path = ? AND ledger_symbol != ?
        """,
        [increment.ledger_symbol, increment.source_path, increment.ledger_symbol],
    )


def _insert_event_batch(
    connection: duckdb.DuckDBPyConnection,
    rows: tuple[tuple[object, ...], ...],
) -> None:
    columns = {
        name: [row[index] for row in rows] for index, name in enumerate(_EVENT_COLUMNS)
    }
    connection.register("cohort_import_batch", pa.table(columns))
    try:
        connection.execute(_INSERT_SQL)
    finally:
        connection.unregister("cohort_import_batch")


def _source_state(
    connection: duckdb.DuckDBPyConnection,
    source: str,
) -> _SourceState | None:
    row = connection.execute(
        """
        SELECT imported_bytes, prefix_sha256, imported_rows
        FROM cohort_live_sources WHERE source_path = ?
        """,
        [source],
    ).fetchone()
    return None if row is None else _SourceState(int(row[0]), str(row[1]), int(row[2]))


def _event_count(connection: duckdb.DuckDBPyConnection) -> int:
    row = connection.execute("SELECT count(*) FROM cohort_live_events").fetchone()
    if row is None:
        raise RuntimeError("cohort event count returned no row")
    return int(row[0])


def _ledger_symbol(path: Path) -> str:
    if path.stem == "decisions":
        return "PORTFOLIO"
    if ":" not in path.stem:
        return path.stem.upper()
    with path.open("rb") as handle:
        for raw in handle:
            value = _mapping(json.loads(raw), "cohort ledger row")
            if value.get("event_type") != "configuration_identity":
                continue
            payload = _mapping(value.get("payload"), "configuration identity payload")
            symbol = _text(payload, "symbol")
            if symbol.casefold() != path.stem.casefold():
                raise ValueError(
                    f"cohort ledger symbol {symbol!r} does not match "
                    f"filename {path.name!r}"
                )
            return symbol
    raise ValueError(
        f"namespaced cohort ledger lacks configuration_identity symbol: {path}"
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"cohort {field} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"cohort {label} must be boolean")
    return value


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("cohort observed_at_utc must include an offset")
    return parsed
