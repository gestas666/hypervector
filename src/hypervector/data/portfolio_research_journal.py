"""Append-only portfolio research hypothesis and decision revisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re

import duckdb

PORTFOLIO_RESEARCH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS portfolio_research_revisions (
    revision_id VARCHAR PRIMARY KEY,
    hypothesis_id VARCHAR NOT NULL,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    supersedes_revision_id VARCHAR,
    created_at_utc TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    hypothesis VARCHAR NOT NULL,
    decision VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL,
    falsifier VARCHAR NOT NULL,
    evidence JSON NOT NULL,
    metrics JSON NOT NULL,
    limitations JSON NOT NULL,
    source_record_path VARCHAR NOT NULL,
    source_record_sha256 VARCHAR NOT NULL,
    source_record_bytes UBIGINT NOT NULL,
    execution_authority VARCHAR NOT NULL CHECK (execution_authority = 'none'),
    automatic_promotion BOOLEAN NOT NULL CHECK (NOT automatic_promotion),
    runtime_strategy_changed BOOLEAN NOT NULL CHECK (NOT runtime_strategy_changed),
    UNIQUE (hypothesis_id, revision_number)
);
"""

_STATUSES = frozenset({"observe", "retain", "candidate", "retire", "reject"})
_CONFIDENCE = frozenset({"low", "low_medium", "medium", "medium_high", "high"})
_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PortfolioResearchAppendReport:
    """Identity and insertion result for one immutable revision."""

    revision_id: str
    hypothesis_id: str
    revision_number: int
    inserted: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _EvidenceReference:
    path: str
    role: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _Revision:
    revision_id: str
    hypothesis_id: str
    revision_number: int
    supersedes_revision_id: str | None
    created_at_utc: datetime
    strategy_id: str
    symbol: str
    status: str
    hypothesis: str
    decision: str
    confidence: str
    falsifier: str
    evidence: tuple[_EvidenceReference, ...]
    metrics: dict[str, object]
    limitations: tuple[str, ...]
    source_record_path: str
    source_record_sha256: str
    source_record_bytes: int


def append_portfolio_research_revision(
    database_path: Path,
    record_path: Path,
) -> PortfolioResearchAppendReport:
    """Validate and append one source-backed, report-only research revision."""
    revision = _load_revision(record_path)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(PORTFOLIO_RESEARCH_SCHEMA_SQL)
        existing = _existing_revision(connection, revision)
        if existing is not None:
            return PortfolioResearchAppendReport(
                revision.revision_id,
                revision.hypothesis_id,
                revision.revision_number,
                False,
            )
        _validate_revision_chain(connection, revision)
        _insert_revision(connection, revision)
    return PortfolioResearchAppendReport(
        revision.revision_id,
        revision.hypothesis_id,
        revision.revision_number,
        True,
    )


def portfolio_research_summary(database_path: Path) -> dict[str, int]:
    """Return counts for durable hypotheses, revisions, and evidence references."""
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(PORTFOLIO_RESEARCH_SCHEMA_SQL)
        row = connection.execute(
            """
            SELECT count(*), count(DISTINCT hypothesis_id),
                   sum(CAST(json_array_length(evidence) AS UBIGINT))
            FROM portfolio_research_revisions
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("portfolio research summary returned no row")
    revisions, hypotheses, evidence = (int(row[0]), int(row[1]), int(row[2] or 0))
    return {
        "current_hypotheses": hypotheses,
        "evidence_references": evidence,
        "hypotheses": hypotheses,
        "revisions": revisions,
    }


def portfolio_research_history(
    database_path: Path,
    hypothesis_id: str,
) -> dict[str, object]:
    """Return ordered revisions and current evidence-integrity observations."""
    _identity(hypothesis_id, "hypothesis_id")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(PORTFOLIO_RESEARCH_SCHEMA_SQL)
        rows = connection.execute(
            """
            SELECT revision_id, revision_number, supersedes_revision_id,
                   created_at_utc, strategy_id, symbol, status, hypothesis,
                   decision, confidence, falsifier, evidence, metrics, limitations
            FROM portfolio_research_revisions
            WHERE hypothesis_id = ? ORDER BY revision_number
            """,
            [hypothesis_id],
        ).fetchall()
    revisions, integrity = _history_rows(rows)
    current = revisions[-1]["revision_id"] if revisions else None
    return {
        "automatic_promotion": False,
        "current_revision_id": current,
        "evidence_integrity": integrity,
        "execution_authority": "none",
        "hypothesis_id": hypothesis_id,
        "revisions": revisions,
        "runtime_strategy_changed": False,
    }


def _load_revision(record_path: Path) -> _Revision:
    path = record_path.resolve()
    raw = path.read_bytes()
    source = _mapping(json.loads(raw), "research revision")
    _exact_contract(source)
    evidence = _evidence_references(source.get("evidence"), path.parent)
    fields = _revision_fields(source, evidence)
    revision_id = _canonical_sha256(fields)
    return _Revision(
        revision_id=revision_id,
        source_record_path=str(path),
        source_record_sha256=_bytes_sha256(raw),
        source_record_bytes=len(raw),
        **fields,
    )


def _revision_fields(
    source: Mapping[str, object],
    evidence: tuple[_EvidenceReference, ...],
) -> dict[str, object]:
    revision_number = _positive_integer(
        source.get("revision_number"), "revision_number"
    )
    supersedes = _optional_sha256(source.get("supersedes_revision_id"))
    if revision_number == 1 and supersedes is not None:
        raise ValueError("revision 1 cannot supersede another revision")
    return {
        "hypothesis_id": _identity(_text(source, "hypothesis_id"), "hypothesis_id"),
        "revision_number": revision_number,
        "supersedes_revision_id": supersedes,
        "created_at_utc": _timestamp(_text(source, "created_at_utc")),
        "strategy_id": _text(source, "strategy_id"),
        "symbol": _text(source, "symbol").upper(),
        "status": _choice(source, "status", _STATUSES),
        "hypothesis": _text(source, "hypothesis"),
        "decision": _text(source, "decision"),
        "confidence": _choice(source, "confidence", _CONFIDENCE),
        "falsifier": _text(source, "falsifier"),
        "evidence": evidence,
        "metrics": _json_object(source.get("metrics"), "metrics"),
        "limitations": _text_sequence(source.get("limitations"), "limitations"),
    }


def _exact_contract(source: Mapping[str, object]) -> None:
    if source.get("schema_version") != 1:
        raise ValueError("research schema_version must equal 1")
    if source.get("execution_authority") != "none":
        raise ValueError("research execution_authority must equal none")
    if source.get("automatic_promotion") is not False:
        raise ValueError("research automatic_promotion must be false")
    if source.get("runtime_strategy_changed") is not False:
        raise ValueError("research runtime_strategy_changed must be false")


def _evidence_references(
    value: object,
    base: Path,
) -> tuple[_EvidenceReference, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("research evidence must be a non-empty list")
    return tuple(_evidence_reference(item, base) for item in value)


def _evidence_reference(value: object, base: Path) -> _EvidenceReference:
    row = _mapping(value, "research evidence reference")
    path = (base / _text(row, "path")).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"research evidence file is missing: {path}")
    expected_sha = _required_sha256(row.get("sha256"), "evidence sha256")
    expected_bytes = _nonnegative_integer(row.get("bytes"), "evidence bytes")
    content = path.read_bytes()
    if _bytes_sha256(content) != expected_sha:
        raise ValueError(f"evidence SHA-256 mismatch: {path}")
    if len(content) != expected_bytes:
        raise ValueError(f"evidence byte-count mismatch: {path}")
    return _EvidenceReference(
        str(path), _text(row, "role"), expected_sha, expected_bytes
    )


def _existing_revision(
    connection: duckdb.DuckDBPyConnection,
    revision: _Revision,
) -> str | None:
    row = connection.execute(
        """SELECT revision_id FROM portfolio_research_revisions
           WHERE hypothesis_id = ? AND revision_number = ?""",
        [revision.hypothesis_id, revision.revision_number],
    ).fetchone()
    if row is None:
        return None
    if row[0] != revision.revision_id:
        raise ValueError("portfolio research revision identity conflict")
    return str(row[0])


def _validate_revision_chain(
    connection: duckdb.DuckDBPyConnection,
    revision: _Revision,
) -> None:
    prior_number = revision.revision_number - 1
    if prior_number == 0:
        return
    row = connection.execute(
        """SELECT revision_id, strategy_id, symbol, created_at_utc
           FROM portfolio_research_revisions
           WHERE hypothesis_id = ? AND revision_number = ?""",
        [revision.hypothesis_id, prior_number],
    ).fetchone()
    if row is None or revision.supersedes_revision_id != row[0]:
        raise ValueError(
            f"revision {revision.revision_number} must supersede revision {prior_number}"
        )
    if revision.strategy_id != row[1] or revision.symbol != row[2]:
        raise ValueError("research revision chain changed strategy or symbol identity")
    if revision.created_at_utc < row[3]:
        raise ValueError("research revision timestamp predates the superseded revision")


def _insert_revision(
    connection: duckdb.DuckDBPyConnection,
    revision: _Revision,
) -> None:
    connection.execute(
        """INSERT INTO portfolio_research_revisions VALUES (
           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', FALSE, FALSE
        )""",
        [
            revision.revision_id,
            revision.hypothesis_id,
            revision.revision_number,
            revision.supersedes_revision_id,
            revision.created_at_utc,
            revision.strategy_id,
            revision.symbol,
            revision.status,
            revision.hypothesis,
            revision.decision,
            revision.confidence,
            revision.falsifier,
            _json(revision.evidence),
            _json(revision.metrics),
            _json(revision.limitations),
            revision.source_record_path,
            revision.source_record_sha256,
            revision.source_record_bytes,
        ],
    )


def _history_rows(
    rows: Sequence[tuple[object, ...]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    revisions: list[dict[str, object]] = []
    integrity = {"changed": 0, "matching": 0, "missing": 0}
    for row in rows:
        evidence = _reported_evidence(json.loads(str(row[11])), integrity)
        revisions.append(
            {
                "revision_id": row[0],
                "revision_number": row[1],
                "supersedes_revision_id": row[2],
                "created_at_utc": row[3].isoformat(),
                "strategy_id": row[4],
                "symbol": row[5],
                "status": row[6],
                "hypothesis": row[7],
                "decision": row[8],
                "confidence": row[9],
                "falsifier": row[10],
                "evidence": evidence,
                "metrics": json.loads(str(row[12])),
                "limitations": json.loads(str(row[13])),
            }
        )
    return revisions, integrity


def _reported_evidence(
    value: object,
    totals: dict[str, int],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise RuntimeError("stored portfolio research evidence is not a list")
    result: list[dict[str, object]] = []
    for item in value:
        row = dict(_mapping(item, "stored evidence"))
        integrity = _file_integrity(row)
        totals[integrity] += 1
        row["integrity"] = integrity
        result.append(row)
    return result


def _file_integrity(row: Mapping[str, object]) -> str:
    path = Path(_text(row, "path"))
    if not path.is_file():
        return "missing"
    content = path.read_bytes()
    matches = len(content) == row.get("bytes") and _bytes_sha256(content) == row.get(
        "sha256"
    )
    return "matching" if matches else "changed"


def _canonical_sha256(fields: Mapping[str, object]) -> str:
    encoded = json.dumps(
        fields, sort_keys=True, separators=(",", ":"), default=_json_default
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=_json_default
    )


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, _EvidenceReference):
        return value.to_dict()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(
        f"unsupported portfolio research JSON value: {type(value).__name__}"
    )


def _json_object(value: object, label: str) -> dict[str, object]:
    result = dict(_mapping(value, label))
    _json(result)
    return result


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"research {label} must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"research {label} entries must be non-empty text")
    return tuple(item.strip() for item in value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with text keys")
    return value


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"research {field} must be non-empty text")
    return value.strip()


def _choice(row: Mapping[str, object], field: str, choices: frozenset[str]) -> str:
    value = _text(row, field)
    if value not in choices:
        raise ValueError(f"research {field} must be one of {sorted(choices)}")
    return value


def _identity(value: str, label: str) -> str:
    if _IDENTITY.fullmatch(value) is None:
        raise ValueError(f"research {label} must be a lowercase stable identity")
    return value


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("research created_at_utc must include an offset")
    return parsed.astimezone(UTC)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"research {label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"research {label} must be a nonnegative integer")
    return value


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"research {label} must be a lowercase SHA-256")
    return value


def _optional_sha256(value: object) -> str | None:
    return None if value is None else _required_sha256(value, "supersedes_revision_id")


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
