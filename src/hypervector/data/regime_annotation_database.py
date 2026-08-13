"""Immutable DuckDB ingestion for exact Hypertrader regime annotations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hypertrader_label_evidence import load_label_evidence
from hypervector.research.hypertrader_source_adapter import (
    LEGACY_HYPERTRADER_REVISION,
    PINNED_HYPERTRADER_REVISION,
)

_REQUIRED_COLUMNS = {
    "available_at",
    "primary_code",
    "secondary_code",
    "confidence",
    "raw_primary_code",
    "raw_secondary_code",
    "raw_confidence",
    "volume_ratio",
}
_DATABASE_COLUMNS = (
    "revision",
    "classifier_role",
    "symbol",
    "timeframe",
    "label_time_utc",
    "available_at",
    "primary_code",
    "secondary_code",
    "confidence",
    "raw_primary_code",
    "raw_secondary_code",
    "raw_confidence",
    "volume_ratio",
    "labels_sha256",
    "metadata_sha256",
    "report_only",
    "execution_authority",
)
_VOLUME_RATIO_IDENTITY_TOLERANCE = 1e-12


@dataclass(frozen=True)
class RegimeAnnotationIngestReport:
    """Counts and immutable revision identity for one label import."""

    revision: str
    source_labels: int
    imported_labels: int
    skipped_labels: int
    overlapping_shadow_bars: int
    disagreements: int

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _Annotation:
    values: tuple[object, ...]


def ingest_hypertrader_labels(
    database_path: Path,
    labels_path: Path,
    metadata_path: Path,
) -> RegimeAnnotationIngestReport:
    """Import verified source labels as observe-only research annotations."""
    evidence = load_label_evidence(labels_path, metadata_path)
    role = _classifier_role(evidence.revision)
    metadata = _metadata(metadata_path)
    _validate_contract(metadata)
    annotations = _annotations(
        labels_path,
        metadata_path,
        revision=evidence.revision,
        role=role,
    )
    with duckdb.connect(str(database_path)) as connection:
        before = _count(connection, "hypertrader_regime_annotations")
        _insert_annotations(connection, annotations)
        after = _count(connection, "hypertrader_regime_annotations")
        overlap = _count(connection, "shadow_hypertrader_regime_comparison")
        disagreements = _comparison_disagreements(connection)
    imported = after - before
    return RegimeAnnotationIngestReport(
        revision=evidence.revision,
        source_labels=len(annotations),
        imported_labels=imported,
        skipped_labels=len(annotations) - imported,
        overlapping_shadow_bars=overlap,
        disagreements=disagreements,
    )


def regime_comparison_summary(database_path: Path) -> dict[str, object]:
    """Summarize causal strict, legacy, and backend label disagreement."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        completed = _count(connection, "shadow_completed_5m_bars")
        coverage = _annotation_coverage(connection)
        archive_parity = _archive_bar_parity(connection)
        row = connection.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE label_disagrees),
                   count(*) FILTER (
                       WHERE backend_primary IS DISTINCT FROM strict_primary
                   ),
                   count(*) FILTER (
                       WHERE backend_primary IS DISTINCT FROM legacy_primary
                   ),
                   min(bar_open_at), max(bar_open_at)
            FROM shadow_hypertrader_regime_comparison
            """
        ).fetchone()
    if row is None or not all(isinstance(value, int) for value in row[:4]):
        raise RuntimeError("invalid Hypertrader comparison summary")
    compared = int(row[0])
    return {
        "report_only": True,
        "execution_authority": "none",
        "completed_shadow_5m_bars": completed,
        "compared_bars": compared,
        "unlabeled_completed_bars": completed - coverage["strict_compared_bars"],
        **coverage,
        "strict_legacy_disagreements": int(row[1]),
        "backend_strict_disagreements": int(row[2]),
        "backend_legacy_disagreements": int(row[3]),
        **archive_parity,
        "comparison_start_utc": _utc_text(row[4]),
        "comparison_end_utc": _utc_text(row[5]),
    }


def _annotation_coverage(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    """Count causal strict, legacy, and dual annotation coverage separately."""
    row = connection.execute(
        """
        SELECT count(*) FILTER (WHERE strict.label_time_utc IS NOT NULL),
               count(*) FILTER (WHERE legacy.label_time_utc IS NOT NULL),
               count(*) FILTER (
                   WHERE strict.label_time_utc IS NOT NULL
                     AND legacy.label_time_utc IS NOT NULL
               )
        FROM shadow_completed_5m_bars AS bars
        LEFT JOIN hypertrader_regime_annotations AS strict
          ON strict.symbol = bars.symbol
         AND strict.timeframe = '5m'
         AND strict.classifier_role = 'strict'
         AND strict.label_time_utc = bars.bar_open_at
         AND strict.available_at <= bars.available_at
        LEFT JOIN hypertrader_regime_annotations AS legacy
          ON legacy.symbol = bars.symbol
         AND legacy.timeframe = '5m'
         AND legacy.classifier_role = 'legacy'
         AND legacy.label_time_utc = bars.bar_open_at
         AND legacy.available_at <= bars.available_at
        """
    ).fetchone()
    if row is None or not all(isinstance(value, int) for value in row):
        raise RuntimeError("invalid regime annotation coverage")
    strict, legacy, dual = (int(value) for value in row)
    completed = _count(connection, "shadow_completed_5m_bars")
    return {
        "strict_compared_bars": strict,
        "legacy_compared_bars": legacy,
        "dual_compared_bars": dual,
        "strict_unlabeled_completed_bars": completed - strict,
        "legacy_unlabeled_completed_bars": completed - legacy,
    }


def _archive_bar_parity(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    row = connection.execute(
        """
        WITH bounds AS (
            SELECT min(bar_open_at) AS start_at, max(bar_open_at) AS end_at
            FROM shadow_completed_5m_bars
        ), archive AS (
            SELECT trades.symbol,
                   time_bucket(INTERVAL '5 minutes', ts_utc) AS bar_open_at,
                   arg_min(price, ts_utc) AS open,
                   max(price) AS high,
                   min(price) AS low,
                   arg_max(price, ts_utc) AS close,
                   sum(size) AS volume
            FROM replay_public_trades AS trades, bounds
            WHERE ts_utc >= start_at AND ts_utc < end_at + INTERVAL 5 MINUTES
            GROUP BY trades.symbol, time_bucket(INTERVAL '5 minutes', ts_utc)
        ), parity AS (
            SELECT archive.symbol IS NOT NULL AS comparable,
                   shadow.open = archive.open
                   AND shadow.high = archive.high
                   AND shadow.low = archive.low
                   AND shadow.close = archive.close
                   AND abs(shadow.volume - archive.volume) <= 1e-9 AS exact
            FROM shadow_completed_5m_bars AS shadow
            LEFT JOIN archive USING (symbol, bar_open_at)
        )
        SELECT count(*) FILTER (WHERE comparable),
               count(*) FILTER (WHERE comparable AND exact)
        FROM parity
        """
    ).fetchone()
    if row is None or not all(isinstance(value, int) for value in row):
        raise RuntimeError("invalid archive bar parity summary")
    comparable, exact = (int(row[0]), int(row[1]))
    return {
        "archive_comparable_bars": comparable,
        "archive_exact_ohlcv_bars": exact,
        "archive_ohlcv_mismatches": comparable - exact,
    }


def _metadata(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("label metadata must contain a JSON object")
    return value


def _validate_contract(metadata: dict[str, object]) -> None:
    required = {
        "report_only": True,
        "runtime_strategy_changed": False,
        "model_authority": "observe",
    }
    mismatches = [
        key for key, expected in required.items() if metadata.get(key) != expected
    ]
    if mismatches:
        raise ValueError(
            "Hypertrader labels violate annotation-only contract: "
            + ", ".join(mismatches)
        )


def _classifier_role(revision: str) -> str:
    if revision == PINNED_HYPERTRADER_REVISION:
        return "strict"
    if revision == LEGACY_HYPERTRADER_REVISION:
        return "legacy"
    raise ValueError(f"unsupported Hypertrader annotation revision: {revision}")


def _annotations(
    labels_path: Path,
    metadata_path: Path,
    *,
    revision: str,
    role: str,
) -> tuple[_Annotation, ...]:
    labels = pd.read_parquet(labels_path)
    missing = _REQUIRED_COLUMNS.difference(labels.columns)
    if missing:
        raise ValueError(f"Hypertrader labels missing: {sorted(missing)}")
    _validate_index(labels)
    label_evidence = file_evidence(labels_path)
    metadata_evidence = file_evidence(metadata_path)
    label_sha = str(label_evidence["sha256"])
    metadata_sha = str(metadata_evidence["sha256"])
    return tuple(
        _annotation(
            timestamp,
            row,
            revision=revision,
            role=role,
            label_sha=label_sha,
            metadata_sha=metadata_sha,
        )
        for timestamp, row in labels.iterrows()
    )


def _validate_index(labels: pd.DataFrame) -> None:
    index = labels.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("Hypertrader labels require a timezone-aware index")
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Hypertrader label timestamps must be unique and ordered")
    if not index.floor("5min").equals(index):
        raise ValueError("Hypertrader label timestamps must align to five minutes")


def _annotation(
    timestamp: object,
    row: pd.Series,
    *,
    revision: str,
    role: str,
    label_sha: str,
    metadata_sha: str,
) -> _Annotation:
    label_time = pd.Timestamp(timestamp).tz_convert("UTC")
    available_at = pd.Timestamp(row["available_at"]).tz_convert("UTC")
    if available_at != label_time + pd.Timedelta(minutes=5):
        raise ValueError("Hypertrader label availability must lag exactly five minutes")
    label_values: tuple[object, ...] = (
        str(row["primary_code"]),
        _nullable_text(row["secondary_code"]),
        float(row["confidence"]),
        str(row["raw_primary_code"]),
        _nullable_text(row["raw_secondary_code"]),
        float(row["raw_confidence"]),
        _nullable_float(row["volume_ratio"]),
    )
    return _Annotation(
        values=(
            revision,
            role,
            "BTC",
            "5m",
            label_time.to_pydatetime(),
            available_at.to_pydatetime(),
            *label_values,
            label_sha,
            metadata_sha,
            True,
            "none",
        )
    )


def _insert_annotations(
    connection: duckdb.DuckDBPyConnection,
    annotations: tuple[_Annotation, ...],
) -> None:
    frame = pd.DataFrame(
        [annotation.values for annotation in annotations],
        columns=list(_DATABASE_COLUMNS),
    )
    connection.register("incoming_regime_annotations", frame)
    connection.execute("BEGIN TRANSACTION")
    committed = False
    try:
        _assert_no_conflicts(connection)
        connection.execute(
            """
            INSERT INTO hypertrader_regime_annotations
            SELECT *, current_timestamp
            FROM incoming_regime_annotations
            ON CONFLICT DO NOTHING
            """,
        )
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            connection.execute("ROLLBACK")
        connection.unregister("incoming_regime_annotations")


def _assert_no_conflicts(connection: duckdb.DuckDBPyConnection) -> None:
    row = connection.execute(
        """
        SELECT count(*)
        FROM hypertrader_regime_annotations AS existing
        INNER JOIN incoming_regime_annotations AS incoming
            USING (revision, symbol, timeframe, label_time_utc)
        WHERE existing.available_at IS DISTINCT FROM incoming.available_at
           OR existing.primary_code IS DISTINCT FROM incoming.primary_code
           OR existing.secondary_code IS DISTINCT FROM incoming.secondary_code
           OR existing.confidence IS DISTINCT FROM incoming.confidence
           OR existing.raw_primary_code IS DISTINCT FROM incoming.raw_primary_code
           OR existing.raw_secondary_code IS DISTINCT FROM incoming.raw_secondary_code
           OR existing.raw_confidence IS DISTINCT FROM incoming.raw_confidence
           OR (
               existing.volume_ratio IS DISTINCT FROM incoming.volume_ratio
               AND (
                   existing.volume_ratio IS NULL
                   OR incoming.volume_ratio IS NULL
                   OR abs(existing.volume_ratio - incoming.volume_ratio) > ?
               )
           )
        """,
        [_VOLUME_RATIO_IDENTITY_TOLERANCE],
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid Hypertrader annotation conflict count")
    if row[0] > 0:
        raise ValueError(
            "conflicting Hypertrader annotation for revision and timestamp"
        )


def _nullable_text(value: object) -> str | None:
    return None if pd.isna(value) else str(value)


def _nullable_float(value: object) -> float | None:
    return None if pd.isna(value) else float(value)


def _utc_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuntimeError("comparison timestamp is not a datetime")
    return value.astimezone(UTC).isoformat()


def _count(connection: duckdb.DuckDBPyConnection, relation: str) -> int:
    allowed = {
        "hypertrader_regime_annotations",
        "shadow_completed_5m_bars",
        "shadow_hypertrader_regime_comparison",
    }
    if relation not in allowed:
        raise ValueError(f"unsupported annotation relation: {relation}")
    row = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise RuntimeError(f"invalid row count for {relation}")
    return row[0]


def _comparison_disagreements(connection: duckdb.DuckDBPyConnection) -> int:
    row = connection.execute(
        "SELECT count(*) FROM shadow_hypertrader_regime_comparison WHERE label_disagrees"
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid Hypertrader disagreement count")
    return row[0]
