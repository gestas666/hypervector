"""Select canonical DuckDB or verified gzip evidence for maker research."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    OxaArchiveBundle,
    verified_archive_bundles,
)
from hypervector.research.maker_replay_stream import (
    MakerReplayEvidenceChunk,
    archive_evidence_chunks,
)
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    database_evidence_chunks,
)


@dataclass(frozen=True)
class MakerReplayEvidence:
    """One replay stream and its explicit source/coverage summary."""

    chunks: Iterable[MakerReplayEvidenceChunk]
    summary: dict[str, object]


def maker_replay_evidence(
    data_root: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    include_trades: bool,
    database_path: Path | None = None,
) -> MakerReplayEvidence:
    """Prefer materialized canonical evidence, retaining verified gzip fallback."""
    candidate = database_path or data_root / "research" / "market.duckdb"
    if candidate.is_file():
        if start == end:
            return MakerReplayEvidence((), _empty_database_summary(candidate))
        config = ResearchReplayConfig(candidate, symbol, start, end)
        return MakerReplayEvidence(
            database_evidence_chunks(config, include_trades=include_trades),
            _database_summary(config),
        )
    if database_path is not None:
        raise FileNotFoundError(f"research database is missing: {database_path}")
    bundles = verified_archive_bundles(
        OxaArchiveAuditConfig(symbol, start, end, data_root)
    )
    return MakerReplayEvidence(
        archive_evidence_chunks(bundles, include_trades=include_trades),
        _archive_summary(bundles),
    )


def _empty_database_summary(database_path: Path) -> dict[str, object]:
    return {
        "data_source": "duckdb_canonical_replay",
        "database_path": str(database_path.resolve()),
        "hourly_windows": 0,
        "source_book_snapshots": 0,
        "source_public_trades": 0,
        "book_snapshots": 0,
        "public_trades": 0,
        "excluded_source_book_rows": 0,
        "excluded_source_trade_rows": 0,
        "empty_book_windows": 0,
        "empty_trade_windows": 0,
        "checksums_verified": True,
    }


def _database_summary(config: ResearchReplayConfig) -> dict[str, object]:
    with duckdb.connect(str(config.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        archive = connection.execute(
            """
            SELECT count(*), sum(book_rows), sum(trade_rows),
                   count(*) FILTER (WHERE book_rows = 0),
                   count(*) FILTER (WHERE trade_rows = 0)
            FROM archive_bundles
            WHERE symbol = ? AND start_utc >= ? AND end_utc <= ?
            """,
            [config.symbol, config.start, config.end],
        ).fetchone()
        books = _window_count(connection, "replay_book_snapshots", config)
        trades = _window_count(connection, "replay_public_trades", config)
    values = _archive_values(archive)
    return {
        "data_source": "duckdb_canonical_replay",
        "database_path": str(config.database_path.resolve()),
        "hourly_windows": values[0],
        "source_book_snapshots": values[1],
        "source_public_trades": values[2],
        "book_snapshots": books,
        "public_trades": trades,
        "excluded_source_book_rows": values[1] - books,
        "excluded_source_trade_rows": values[2] - trades,
        "empty_book_windows": values[3],
        "empty_trade_windows": values[4],
        "checksums_verified": True,
    }


def _window_count(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    config: ResearchReplayConfig,
) -> int:
    if table not in {"replay_book_snapshots", "replay_public_trades"}:
        raise ValueError(f"unsupported replay table: {table}")
    sql = (
        """
        SELECT count(*) FROM (
            SELECT trade_id FROM public_trades
            WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
            QUALIFY row_number() OVER (
                PARTITION BY symbol, trade_id ORDER BY bundle_id
            ) = 1
        )
        """
        if table == "replay_public_trades"
        else f"SELECT count(*) FROM {table} WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?"
    )
    row = connection.execute(
        sql,
        [config.symbol, config.start, config.end],
    ).fetchone()
    return _required_int(row, table)


def _archive_values(row: tuple[object, ...] | None) -> tuple[int, int, int, int, int]:
    if row is None or len(row) != 5:
        raise RuntimeError("research database returned invalid archive summary")
    values = tuple(0 if value is None else value for value in row)
    if not all(
        isinstance(value, int) and not isinstance(value, bool) for value in values
    ):
        raise RuntimeError("research database archive summary must contain integers")
    return values


def _required_int(row: tuple[object, ...] | None, label: str) -> int:
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise RuntimeError(f"research database returned invalid count: {label}")
    return row[0]


def _archive_summary(bundles: tuple[OxaArchiveBundle, ...]) -> dict[str, object]:
    return {
        "data_source": "verified_hourly_gzip",
        "hourly_windows": len(bundles),
        "book_snapshots": sum(bundle.book_rows for bundle in bundles),
        "public_trades": sum(bundle.trade_rows for bundle in bundles),
        "empty_book_windows": sum(bundle.book_rows == 0 for bundle in bundles),
        "empty_trade_windows": sum(bundle.trade_rows == 0 for bundle in bundles),
        "checksums_verified": True,
    }
