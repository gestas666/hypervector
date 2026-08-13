"""Idempotent DuckDB ingestion for immutable parts and append-only gap logs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from hypervector.data.live_event_research_sql import (
    LIVE_CONTEXT_INSERT_SQL,
    LIVE_L2_INSERT_SQL,
    LIVE_TRADE_INSERT_SQL,
)

_DATASET_DIRECTORIES = {
    "l2": "l2.parquet",
    "trades": "trades.parquet",
    "asset_context": "asset_context.parquet",
}
_DATASET_TABLES = {
    "l2": "live_book_snapshots",
    "trades": "live_public_trades",
    "asset_context": "live_asset_contexts",
    "gaps": "live_stream_gaps",
}


@dataclass(frozen=True)
class LiveEventIngestReport:
    """Counts from one immutable live-event archive import."""

    source_files: int
    imported_files: int
    skipped_files: int
    l2_rows: int
    trade_rows: int
    asset_context_rows: int
    gap_rows: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _EventFile:
    file_id: str
    symbol: str
    utc_date: date
    dataset: str
    path: Path
    byte_count: int
    row_count: int
    sha256: str
    previous_file_id: str | None = None
    previous_row_count: int = 0

    def record(self) -> tuple[object, ...]:
        """Return values in live_event_files column order."""
        return (
            self.file_id,
            self.symbol,
            self.utc_date,
            self.dataset,
            str(self.path),
            self.byte_count,
            self.row_count,
            self.sha256,
        )

    def imported_rows(self) -> int:
        """Return newly observed rows, excluding an append-only prior version."""
        return self.row_count - self.previous_row_count


def ingest_live_event_archive(
    database_path: Path,
    data_root: Path,
    symbol: str,
) -> LiveEventIngestReport:
    """Verify and atomically ingest every unseen live event file."""
    files = _discover_files(data_root, symbol)
    with duckdb.connect(str(database_path)) as connection:
        pending = _pending_files(connection, files)
        if pending:
            _ingest_pending(connection, pending)
    counts = _dataset_counts(pending)
    return LiveEventIngestReport(
        source_files=len(files),
        imported_files=len(pending),
        skipped_files=len(files) - len(pending),
        l2_rows=counts["l2"],
        trade_rows=counts["trades"],
        asset_context_rows=counts["asset_context"],
        gap_rows=counts["gaps"],
    )


def live_event_summary(database_path: Path) -> dict[str, int]:
    """Return source and canonical row counts for imported live evidence."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        source_trades = _relation_count(connection, "live_public_trades")
        canonical_trades = _relation_count(connection, "replay_live_public_trades")
        overlap = _trade_overlap_counts(connection)
        return {
            "source_files": _relation_count(connection, "live_event_files"),
            "source_l2_rows": _relation_count(connection, "live_book_snapshots"),
            "canonical_l2_rows": _relation_count(
                connection, "replay_live_book_snapshots"
            ),
            "source_trade_rows": source_trades,
            "canonical_trade_rows": canonical_trades,
            "duplicate_trade_rows": source_trades - canonical_trades,
            **overlap,
            "asset_context_rows": _relation_count(connection, "live_asset_contexts"),
            "gap_rows": _relation_count(connection, "live_stream_gaps"),
        }


def _trade_overlap_counts(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
            count(archive.trade_id),
            count(archive.trade_id) FILTER (
                WHERE archive.ts_exchange_ms = live.exchange_ts_ms
                  AND archive.aggressor_side = live.aggressor_side
                  AND archive.price = live.price
                  AND archive.size = live.size
            ),
            count(*) FILTER (WHERE archive.trade_id IS NULL)
        FROM replay_live_public_trades AS live
        LEFT JOIN replay_public_trades AS archive USING (symbol, trade_id)
        """
    ).fetchone()
    if row is None or not all(isinstance(value, int) for value in row):
        raise RuntimeError("invalid archive/live overlap counts")
    return {
        "archive_overlap_trade_rows": int(row[0]),
        "exact_archive_overlap_rows": int(row[1]),
        "canonical_extension_trade_rows": int(row[2]),
    }


def _discover_files(data_root: Path, symbol: str) -> tuple[_EventFile, ...]:
    if not symbol.strip():
        raise ValueError("live event symbol must be non-empty")
    root = data_root / "cache" / "events" / "hyperliquid" / symbol
    paths: list[tuple[str, Path]] = []
    for dataset, directory in _DATASET_DIRECTORIES.items():
        paths.extend(
            (dataset, path) for path in root.glob(f"*/{directory}/part-*.parquet")
        )
    paths.extend(("gaps", path) for path in root.glob("*/gaps.jsonl"))
    return tuple(
        _event_file(path, symbol=symbol, dataset=dataset)
        for dataset, path in sorted(paths, key=lambda item: str(item[1]))
    )


def _event_file(path: Path, *, symbol: str, dataset: str) -> _EventFile:
    resolved = path.resolve()
    digest = _sha256(resolved)
    row_count = (
        _jsonl_rows(resolved)
        if dataset == "gaps"
        else int(pq.ParquetFile(resolved).metadata.num_rows)
    )
    utc_date = date.fromisoformat(
        path.parts[-3] if dataset != "gaps" else path.parts[-2]
    )
    return _EventFile(
        file_id=digest,
        symbol=symbol,
        utc_date=utc_date,
        dataset=dataset,
        path=resolved,
        byte_count=resolved.stat().st_size,
        row_count=row_count,
        sha256=digest,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_prefix(path: Path, byte_count: int) -> str:
    digest = hashlib.sha256()
    remaining = byte_count
    with path.open("rb") as handle:
        while remaining:
            chunk = handle.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise ValueError(f"live gap file was truncated: {path}")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _jsonl_rows(path: Path) -> int:
    return sum(
        bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
    )


def _pending_files(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> tuple[_EventFile, ...]:
    pending: list[_EventFile] = []
    for item in files:
        row = connection.execute(
            "SELECT file_id, dataset, byte_count, row_count, sha256 "
            "FROM live_event_files WHERE source_path = ?",
            [str(item.path)],
        ).fetchone()
        if row is None:
            pending.append(item)
        elif row[0] == item.file_id:
            continue
        elif item.dataset == "gaps" and row[1] == "gaps":
            pending.append(_append_only_gap_version(item, row))
        else:
            raise ValueError(f"live event file changed after ingestion: {item.path}")
    return tuple(pending)


def _append_only_gap_version(
    item: _EventFile,
    previous: tuple[object, ...],
) -> _EventFile:
    old_id, _, old_bytes, old_rows, old_sha = previous
    valid_types = (
        isinstance(old_id, str)
        and isinstance(old_bytes, int)
        and isinstance(old_rows, int)
        and isinstance(old_sha, str)
    )
    if not valid_types:
        raise RuntimeError(f"invalid prior live gap metadata: {item.path}")
    is_extension = (
        item.byte_count > old_bytes
        and item.row_count > old_rows
        and _sha256_prefix(item.path, old_bytes) == old_sha
    )
    if not is_extension:
        raise ValueError(f"live gap file changed non-append-only: {item.path}")
    return replace(
        item,
        previous_file_id=old_id,
        previous_row_count=old_rows,
    )


def _ingest_pending(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    connection.execute("BEGIN TRANSACTION")
    committed = False
    try:
        _remove_replaced_gap_versions(connection, files)
        _prepare_file_map(connection, files)
        _insert_parquet_files(connection, files)
        _insert_gap_files(connection, files)
        _assert_trade_id_consistency(connection)
        _assert_archive_trade_consistency(connection)
        _assert_file_counts(connection, files)
        connection.executemany(
            """
            INSERT INTO live_event_files (
                file_id, symbol, utc_date, dataset, source_path,
                byte_count, row_count, sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [item.record() for item in files],
        )
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            connection.execute("ROLLBACK")


def _remove_replaced_gap_versions(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    previous = [item.previous_file_id for item in files if item.previous_file_id]
    if not previous:
        return
    connection.execute(
        "DELETE FROM live_stream_gaps WHERE file_id IN (SELECT unnest(?))", [previous]
    )
    connection.execute(
        "DELETE FROM live_event_files WHERE file_id IN (SELECT unnest(?))", [previous]
    )


def _prepare_file_map(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE incoming_live_files "
        "(source_path VARCHAR, file_id VARCHAR, dataset VARCHAR)"
    )
    connection.executemany(
        "INSERT INTO incoming_live_files VALUES (?, ?, ?)",
        [(str(item.path), item.file_id, item.dataset) for item in files],
    )


def _insert_parquet_files(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    statements = {
        "l2": LIVE_L2_INSERT_SQL,
        "trades": LIVE_TRADE_INSERT_SQL,
        "asset_context": LIVE_CONTEXT_INSERT_SQL,
    }
    for dataset, statement in statements.items():
        paths = [str(item.path) for item in files if item.dataset == dataset]
        if paths:
            connection.execute(statement, [paths])


def _insert_gap_files(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    rows: list[tuple[object, ...]] = []
    for item in files:
        if item.dataset != "gaps":
            continue
        for raw in item.path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                rows.append(_gap_record(raw, item))
    if rows:
        connection.executemany(
            "INSERT INTO live_stream_gaps VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )


def _gap_record(raw: str, item: _EventFile) -> tuple[object, ...]:
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"live gap row is not an object: {item.path}")
    required = ("symbol", "channel", "detected_ts_ns", "reason")
    missing = [field for field in required if value.get(field) in (None, "")]
    if missing or value.get("symbol") != item.symbol:
        raise ValueError(f"invalid live gap evidence in {item.path}")
    return (
        value["symbol"],
        value["channel"],
        value["detected_ts_ns"],
        value["reason"],
        value.get("previous_exchange_ts_ms"),
        value.get("next_exchange_ts_ms"),
        item.file_id,
    )


def _assert_trade_id_consistency(connection: duckdb.DuckDBPyConnection) -> None:
    row = connection.execute(
        """
        SELECT count(*) FROM (
            SELECT symbol, trade_id
            FROM live_public_trades
            GROUP BY symbol, trade_id
            HAVING count(DISTINCT to_json(struct_pack(
                exchange_ts_ms := exchange_ts_ms,
                aggressor_side := aggressor_side,
                price := price,
                size := size,
                transaction_hash := transaction_hash,
                buyer := buyer,
                seller := seller,
                source := source
            ))) > 1
        )
        """
    ).fetchone()
    if row != (0,):
        raise ValueError("conflicting live public-trade identity")


def _assert_archive_trade_consistency(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    row = connection.execute(
        """
        SELECT count(*)
        FROM replay_public_trades AS archive
        INNER JOIN replay_live_public_trades AS live USING (symbol, trade_id)
        WHERE archive.ts_exchange_ms IS DISTINCT FROM live.exchange_ts_ms
           OR archive.aggressor_side IS DISTINCT FROM live.aggressor_side
           OR archive.price IS DISTINCT FROM live.price
           OR archive.size IS DISTINCT FROM live.size
        """
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid archive/live trade conflict count")
    if row[0] > 0:
        raise ValueError("conflicting archive/live public-trade identity")


def _assert_file_counts(
    connection: duckdb.DuckDBPyConnection,
    files: tuple[_EventFile, ...],
) -> None:
    for item in files:
        table = _DATASET_TABLES[item.dataset]
        row = connection.execute(
            f"SELECT count(*) FROM {table} WHERE file_id = ?", [item.file_id]
        ).fetchone()
        if row != (item.row_count,):
            raise ValueError(f"live event row-count mismatch: {item.path}")


def _dataset_counts(files: tuple[_EventFile, ...]) -> dict[str, int]:
    return {
        dataset: sum(item.imported_rows() for item in files if item.dataset == dataset)
        for dataset in _DATASET_TABLES
    }


def _relation_count(connection: duckdb.DuckDBPyConnection, relation: str) -> int:
    allowed = {
        "live_event_files",
        "live_book_snapshots",
        "replay_live_book_snapshots",
        "live_public_trades",
        "replay_live_public_trades",
        "live_asset_contexts",
        "live_stream_gaps",
    }
    if relation not in allowed:
        raise ValueError(f"unsupported live event relation: {relation}")
    row = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError(f"invalid live event row count: {relation}")
    return row[0]
