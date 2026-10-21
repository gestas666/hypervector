"""DuckDB-backed analytical store for verified market-data evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    OxaArchiveBundle,
    OxaArchiveBundleEvidence,
    iter_archive_bundle_evidence,
)
from hypervector.data.research_archive_provenance import (
    ARCHIVE_PROVENANCE_SCHEMA_SQL,
    LEGACY_ARCHIVE_PROVENANCE_SQL,
)
from hypervector.data.research_database_sql import (
    BOOK_INSERT_SQL,
    SCHEMA_SQL,
    TRADE_INSERT_SQL,
)
from hypervector.data.live_event_research_database import (
    LiveEventIngestReport,
    ingest_live_event_archive,
    live_event_summary,
)
from hypervector.data.live_event_research_sql import LIVE_EVENT_SCHEMA_SQL
from hypervector.data.cohort_research_database import (
    CohortLedgerIngestReport,
    cohort_live_summary,
    ingest_cohort_live_ledger,
)
from hypervector.data.cohort_research_sql import COHORT_LIVE_SCHEMA_SQL
from hypervector.data import portfolio_research_journal as journal
from hypervector.data.shadow_research_database import (
    ShadowLedgerIngestReport,
    ingest_shadow_ledger,
    shadow_summary,
)
from hypervector.data.shadow_trade_attribution import (
    shadow_trade_attribution_summary,
)

DEFAULT_BUNDLE_BATCH_SIZE = 24
NO_TRADE_MANIFEST_SHA256 = hashlib.sha256(b"book_only:no_trade_manifest").hexdigest()


@dataclass(frozen=True)
class ResearchIngestReport:
    """Counts produced by one verified archive ingestion request."""

    imported_bundles: int
    skipped_bundles: int
    book_rows: int
    trade_rows: int

    def to_dict(self) -> dict[str, int]:
        """Return a serialization-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _BundleIdentity:
    bundle_id: str
    fingerprint: str
    book_manifest_sha256: str
    trade_manifest_sha256: str


@dataclass(frozen=True)
class _PendingBundle:
    bundle: OxaArchiveBundle
    identity: _BundleIdentity
    replace_existing: bool = False


class ResearchDatabase:
    """Persist checksum-verified order books and trades in DuckDB."""

    def __init__(self, path: Path) -> None:
        if path.exists() and not path.is_file():
            raise ValueError(f"research database path is not a file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._connect() as connection:
            _create_schema(connection)

    def ingest_archive(
        self,
        config: OxaArchiveAuditConfig,
        *,
        verify_all: bool = False,
    ) -> ResearchIngestReport:
        """Verify and atomically ingest every new bundle in an archive window.

        Every manifest is identity-checked, but per-file checksums run only for
        bundles that will be imported, unless ``verify_all`` re-audits the
        already-ingested ones too. All verification precedes any write.
        """
        with self._connect() as connection:
            pending, skipped = _pending_bundles(
                connection, config, verify_all=verify_all
            )
            for batch in _partition(pending, DEFAULT_BUNDLE_BATCH_SIZE):
                _ingest_bundle_batch(connection, config, batch)
        return ResearchIngestReport(
            len(pending),
            skipped,
            sum(item.bundle.book_rows for item in pending),
            sum(item.bundle.trade_rows for item in pending),
        )

    def replace_changed_archive(
        self,
        config: OxaArchiveAuditConfig,
        *,
        verify_all: bool = False,
    ) -> ResearchIngestReport:
        """Atomically replace changed bundles after explicit source repair."""
        with self._connect() as connection:
            pending, skipped = _replacement_bundles(
                connection, config, verify_all=verify_all
            )
            for batch in _partition(pending, DEFAULT_BUNDLE_BATCH_SIZE):
                _ingest_bundle_batch(connection, config, batch)
        return ResearchIngestReport(
            len(pending),
            skipped,
            sum(item.bundle.book_rows for item in pending),
            sum(item.bundle.trade_rows for item in pending),
        )

    def summary(self) -> dict[str, int]:
        """Return durable row counts for the core research tables."""
        with self._connect() as connection:
            source_books = _table_count(connection, "book_snapshots")
            source_trades = _table_count(connection, "public_trades")
            replay_books = _table_count(connection, "replay_book_snapshots")
            replay_trades = _table_count(connection, "replay_public_trades")
            return {
                "archive_bundles": _table_count(connection, "archive_bundles"),
                "source_book_snapshots": source_books,
                "source_public_trades": source_trades,
                "replay_book_snapshots": replay_books,
                "replay_public_trades": replay_trades,
                "deduplicated_book_rows": source_books - replay_books,
                "deduplicated_trade_rows": source_trades - replay_trades,
            }

    def ingest_shadow_ledger(self, path: Path) -> ShadowLedgerIngestReport:
        """Import append-only no-submit observations into the research store."""
        return ingest_shadow_ledger(self._path, path)

    def shadow_summary(self) -> dict[str, int]:
        """Return report-only shadow observation counts."""
        return shadow_summary(self._path)

    def shadow_trade_attribution_summary(self) -> dict[str, object]:
        """Return causal completed-trade and entry-regime metrics."""
        return shadow_trade_attribution_summary(self._path)

    def ingest_live_event_archive(
        self,
        data_root: Path,
        symbol: str,
    ) -> LiveEventIngestReport:
        """Import immutable public WebSocket evidence for research use."""
        return ingest_live_event_archive(self._path, data_root, symbol)

    def live_event_summary(self) -> dict[str, int]:
        """Return source/canonical counts for public live event evidence."""
        return live_event_summary(self._path)

    def ingest_cohort_live_ledger(self, ledger_root: Path) -> CohortLedgerIngestReport:
        """Import append-only private cohort journals without execution authority."""
        return ingest_cohort_live_ledger(self._path, ledger_root)

    def cohort_live_summary(self) -> dict[str, int]:
        """Return durable cohort source, event, fill, and run counts."""
        return cohort_live_summary(self._path)

    def append_portfolio_research_revision(
        self, record_path: Path
    ) -> journal.PortfolioResearchAppendReport:
        """Append one immutable, report-only portfolio research revision."""
        return journal.append_portfolio_research_revision(self._path, record_path)

    def portfolio_research_summary(self) -> dict[str, int]:
        """Return durable portfolio research journal counts."""
        return journal.portfolio_research_summary(self._path)

    def portfolio_research_history(self, hypothesis_id: str) -> dict[str, object]:
        """Return ordered revisions and evidence integrity for one hypothesis."""
        return journal.portfolio_research_history(self._path, hypothesis_id)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._path))


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(SCHEMA_SQL)
    connection.execute(ARCHIVE_PROVENANCE_SCHEMA_SQL)
    _migrate_hip3_paired_provenance(connection)
    connection.execute(LEGACY_ARCHIVE_PROVENANCE_SQL)
    connection.execute(LIVE_EVENT_SCHEMA_SQL)
    connection.execute(COHORT_LIVE_SCHEMA_SQL)
    connection.execute(journal.PORTFOLIO_RESEARCH_SCHEMA_SQL)


def _migrate_hip3_paired_provenance(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Remove the obsolete HIP-3 books-only constraint without losing rows."""
    obsolete = connection.execute(
        """
        SELECT count(*)
        FROM duckdb_constraints()
        WHERE table_name = 'archive_bundle_provenance'
          AND constraint_type = 'CHECK'
          AND lower(constraint_text) LIKE '%market_family%hip3%book_only%'
        """
    ).fetchone()
    if obsolete is None or obsolete[0] == 0:
        return
    connection.execute("BEGIN TRANSACTION")
    committed = False
    try:
        connection.execute(
            "ALTER TABLE archive_bundle_provenance "
            "RENAME TO archive_bundle_provenance_books_only_legacy"
        )
        connection.execute(ARCHIVE_PROVENANCE_SCHEMA_SQL)
        connection.execute(
            """
            INSERT INTO archive_bundle_provenance
            SELECT * FROM archive_bundle_provenance_books_only_legacy
            """
        )
        connection.execute("DROP TABLE archive_bundle_provenance_books_only_legacy")
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            connection.execute("ROLLBACK")


def _pending_bundles(
    connection: duckdb.DuckDBPyConnection,
    config: OxaArchiveAuditConfig,
    *,
    verify_all: bool = False,
) -> tuple[tuple[_PendingBundle, ...], int]:
    pending: list[_PendingBundle] = []
    skipped = 0
    for evidence in iter_archive_bundle_evidence(config):
        identity = _bundle_identity(config, evidence)
        if _is_ingested(connection, config, evidence, identity):
            skipped += 1
            if verify_all:
                evidence.verify_files()
        else:
            evidence.verify_files()
            pending.append(_PendingBundle(evidence.bundle, identity))
    return tuple(pending), skipped


def _replacement_bundles(
    connection: duckdb.DuckDBPyConnection,
    config: OxaArchiveAuditConfig,
    *,
    verify_all: bool = False,
) -> tuple[tuple[_PendingBundle, ...], int]:
    pending: list[_PendingBundle] = []
    skipped = 0
    for evidence in iter_archive_bundle_evidence(config):
        identity = _bundle_identity(config, evidence)
        stored = _stored_fingerprint(connection, identity.bundle_id)
        if stored == identity.fingerprint:
            skipped += 1
            if verify_all:
                evidence.verify_files()
        else:
            evidence.verify_files()
            replaces = stored is not None
            pending.append(_PendingBundle(evidence.bundle, identity, replaces))
    return tuple(pending), skipped


def _partition(
    bundles: tuple[_PendingBundle, ...],
    size: int,
) -> tuple[tuple[_PendingBundle, ...], ...]:
    return tuple(
        bundles[index : index + size] for index in range(0, len(bundles), size)
    )


def _bundle_identity(
    config: OxaArchiveAuditConfig,
    loaded: OxaArchiveBundleEvidence,
) -> _BundleIdentity:
    bundle = loaded.bundle
    book_sha = loaded.book_manifest_sha256
    trade_sha = loaded.trade_manifest_sha256 or NO_TRADE_MANIFEST_SHA256
    key = _bundle_key(config, bundle)
    bundle_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
    evidence = {
        "key": key,
        "book_manifest_sha256": book_sha,
        "trade_manifest_sha256": trade_sha,
    }
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return _BundleIdentity(
        bundle_id,
        hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        book_sha,
        trade_sha,
    )


def _bundle_key(config: OxaArchiveAuditConfig, bundle: OxaArchiveBundle) -> str:
    base = (
        f"{config.symbol}|{bundle.start.isoformat()}|"
        f"{bundle.end.isoformat()}|{config.depth}"
    )
    if config.market_family == "core" and not config.book_only:
        return base
    return f"{config.market_family}|book_only={config.book_only}|{base}"


def _is_ingested(
    connection: duckdb.DuckDBPyConnection,
    config: OxaArchiveAuditConfig,
    evidence: OxaArchiveBundleEvidence,
    identity: _BundleIdentity,
) -> bool:
    stored = _stored_fingerprint(connection, identity.bundle_id)
    if stored is None:
        return False
    if stored != identity.fingerprint:
        directories = [str(evidence.book_directory)]
        if evidence.trade_directory is not None:
            directories.append(str(evidence.trade_directory))
        raise ValueError(
            "archive bundle identity already exists with different evidence: "
            f"{config.symbol} {evidence.bundle.start.isoformat()} to "
            f"{evidence.bundle.end.isoformat()} (bundle {identity.bundle_id}; "
            f"manifests in {', '.join(directories)}); if the source was repaired "
            "on purpose, rebuild with --replace-changed"
        )
    return True


def _stored_fingerprint(
    connection: duckdb.DuckDBPyConnection,
    bundle_id: str,
) -> str | None:
    row = connection.execute(
        "SELECT fingerprint FROM archive_bundles WHERE bundle_id = ?",
        [bundle_id],
    ).fetchone()
    if row is None:
        return None
    if len(row) != 1 or not isinstance(row[0], str):
        raise RuntimeError(f"archive bundle fingerprint is invalid: {bundle_id}")
    return row[0]


def _ingest_bundle_batch(
    connection: duckdb.DuckDBPyConnection,
    config: OxaArchiveAuditConfig,
    pending: tuple[_PendingBundle, ...],
) -> None:
    connection.execute("BEGIN TRANSACTION")
    committed = False
    try:
        _delete_replaced_bundles(connection, pending)
        _prepare_file_maps(connection)
        _insert_books(connection, pending)
        _insert_trades(connection, pending)
        for item in pending:
            _assert_bundle_counts(connection, item.bundle, item.identity.bundle_id)
            _insert_bundle_record(
                connection,
                config,
                item.bundle,
                item.identity,
            )
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            connection.execute("ROLLBACK")


def _delete_replaced_bundles(
    connection: duckdb.DuckDBPyConnection,
    pending: tuple[_PendingBundle, ...],
) -> None:
    identifiers = [
        (item.identity.bundle_id,) for item in pending if item.replace_existing
    ]
    if not identifiers:
        return
    for table in (
        "book_snapshots",
        "public_trades",
        "archive_bundle_provenance",
        "archive_bundles",
    ):
        connection.executemany(
            f"DELETE FROM {table} WHERE bundle_id = ?",
            identifiers,
        )


def _prepare_file_maps(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE ingest_book_files(path VARCHAR, bundle_id VARCHAR)"
    )
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE ingest_trade_files(path VARCHAR, bundle_id VARCHAR)"
    )


def _insert_books(
    connection: duckdb.DuckDBPyConnection,
    pending: tuple[_PendingBundle, ...],
) -> None:
    files = _file_rows(pending, "book")
    if not files:
        return
    connection.executemany("INSERT INTO ingest_book_files VALUES (?, ?)", files)
    connection.execute(BOOK_INSERT_SQL, [[path for path, _ in files]])


def _insert_trades(
    connection: duckdb.DuckDBPyConnection,
    pending: tuple[_PendingBundle, ...],
) -> None:
    files = _file_rows(pending, "trade")
    if not files:
        return
    connection.executemany("INSERT INTO ingest_trade_files VALUES (?, ?)", files)
    connection.execute(TRADE_INSERT_SQL, [[path for path, _ in files]])


def _file_rows(
    pending: tuple[_PendingBundle, ...],
    kind: str,
) -> list[tuple[str, str]]:
    if kind not in {"book", "trade"}:
        raise ValueError(f"unsupported archive file kind: {kind}")
    rows: list[tuple[str, str]] = []
    for item in pending:
        path = item.bundle.book_path if kind == "book" else item.bundle.trade_path
        if path is not None:
            rows.append((str(path.resolve()), item.identity.bundle_id))
    return rows


def _assert_bundle_counts(
    connection: duckdb.DuckDBPyConnection,
    bundle: OxaArchiveBundle,
    bundle_id: str,
) -> None:
    books = _bundle_row_count(connection, "book_snapshots", bundle_id)
    trades = _bundle_row_count(connection, "public_trades", bundle_id)
    if books != bundle.book_rows or trades != bundle.trade_rows:
        raise ValueError(
            "archive row-count mismatch during ingestion: "
            f"expected books={bundle.book_rows}, trades={bundle.trade_rows}; "
            f"loaded books={books}, trades={trades}"
        )


def _insert_bundle_record(
    connection: duckdb.DuckDBPyConnection,
    config: OxaArchiveAuditConfig,
    bundle: OxaArchiveBundle,
    identity: _BundleIdentity,
) -> None:
    connection.execute(
        """
        INSERT INTO archive_bundles (
            bundle_id, symbol, start_utc, end_utc, depth, book_rows, trade_rows,
            book_manifest_sha256, trade_manifest_sha256, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            identity.bundle_id,
            config.symbol,
            bundle.start,
            bundle.end,
            config.depth,
            bundle.book_rows,
            bundle.trade_rows,
            identity.book_manifest_sha256,
            identity.trade_manifest_sha256,
            identity.fingerprint,
        ],
    )
    book_source = (
        "0xarchive_hyperliquid_hip3_l2"
        if config.market_family == "hip3"
        else "0xarchive_hyperliquid_native_l2"
    )
    connection.execute(
        "INSERT INTO archive_bundle_provenance VALUES (?, ?, ?, ?)",
        [identity.bundle_id, config.market_family, config.book_only, book_source],
    )


def _bundle_row_count(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    bundle_id: str,
) -> int:
    if table not in {"book_snapshots", "public_trades"}:
        raise ValueError(f"unsupported research table: {table}")
    row = connection.execute(
        f"SELECT count(*) FROM {table} WHERE bundle_id = ?",
        [bundle_id],
    ).fetchone()
    return _count_value(row, table)


def _table_count(connection: duckdb.DuckDBPyConnection, table: str) -> int:
    supported = {
        "archive_bundles",
        "book_snapshots",
        "public_trades",
        "replay_book_snapshots",
        "replay_public_trades",
    }
    if table not in supported:
        raise ValueError(f"unsupported research table: {table}")
    row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
    return _count_value(row, table)


def _count_value(row: tuple[object, ...] | None, table: str) -> int:
    if (
        row is None
        or len(row) != 1
        or isinstance(row[0], bool)
        or not isinstance(row[0], int)
    ):
        raise RuntimeError(f"database count query returned invalid result: {table}")
    return row[0]
