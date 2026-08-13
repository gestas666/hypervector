"""Idempotent research ingestion for append-only paper/shadow ledgers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class ShadowLedgerIngestReport:
    """Counts from one report-only shadow-ledger import."""

    source_events: int
    imported_events: int
    skipped_events: int
    regime_observations: int
    completed_5m_bars: int

    def to_dict(self) -> dict[str, int]:
        """Return a JSON-safe report."""
        return asdict(self)


@dataclass(frozen=True)
class _ShadowEvent:
    event_id: str
    source_path: str
    source_line: int
    feed_ts: str
    observed_at: datetime | None
    run_id: str | None
    action: str
    symbol: str | None
    timeframe: str | None
    execution_mode: str
    submitted: bool | None
    place_attempted: bool | None
    payload: str

    def values(self) -> tuple[object, ...]:
        """Return values in the durable table's column order."""
        return (
            self.event_id,
            self.source_path,
            self.source_line,
            self.feed_ts,
            self.observed_at,
            self.run_id,
            self.action,
            self.symbol,
            self.timeframe,
            self.execution_mode,
            self.submitted,
            self.place_attempted,
            self.payload,
        )


def ingest_shadow_ledger(
    database_path: Path,
    ledger_path: Path,
) -> ShadowLedgerIngestReport:
    """Import a paper/shadow JSONL ledger without granting execution authority."""
    events = _load_events(ledger_path)
    with duckdb.connect(str(database_path)) as connection:
        before = _count(connection, "shadow_ledger_events")
        connection.execute("BEGIN TRANSACTION")
        committed = False
        try:
            connection.executemany(
                """
                INSERT INTO shadow_ledger_events (
                    event_id, source_path, source_line, feed_ts, observed_at,
                    run_id, action, symbol, timeframe, execution_mode,
                    submitted, place_attempted, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [event.values() for event in events],
            )
            connection.execute("COMMIT")
            committed = True
        finally:
            if not committed:
                connection.execute("ROLLBACK")
        after = _count(connection, "shadow_ledger_events")
        regimes = _count(connection, "shadow_regime_observations")
        completed = _count(connection, "shadow_completed_5m_bars")
    imported = after - before
    return ShadowLedgerIngestReport(
        source_events=len(events),
        imported_events=imported,
        skipped_events=len(events) - imported,
        regime_observations=regimes,
        completed_5m_bars=completed,
    )


def shadow_summary(database_path: Path) -> dict[str, int]:
    """Return durable observation counts without modifying the database."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        return {
            "shadow_events": _count(connection, "shadow_ledger_events"),
            "regime_observations": _count(connection, "shadow_regime_observations"),
            "completed_5m_bars": _count(connection, "shadow_completed_5m_bars"),
        }


def _load_events(path: Path) -> tuple[_ShadowEvent, ...]:
    if not path.is_file():
        raise FileNotFoundError(f"shadow ledger is missing: {path}")
    events: list[_ShadowEvent] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if raw.strip():
            events.append(_event(path, line_number, raw))
    return tuple(events)


def _event(path: Path, line_number: int, raw: str) -> _ShadowEvent:
    value: object = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"shadow ledger line {line_number} is not an object")
    record = value
    mode = _required_text(record, "execution_mode", line_number)
    if mode not in {"paper", "shadow"}:
        raise ValueError(
            f"shadow ledger line {line_number} must be paper or shadow mode"
        )
    feed_ts = _required_text(record, "feed_ts", line_number)
    action = _required_text(record, "action", line_number)
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return _ShadowEvent(
        event_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        source_path=str(path.resolve()),
        source_line=line_number,
        feed_ts=feed_ts,
        observed_at=_observed_at(feed_ts, line_number),
        run_id=_optional_text(record.get("run_id")),
        action=action,
        symbol=_optional_text(record.get("symbol")),
        timeframe=_optional_text(record.get("timeframe")),
        execution_mode=mode,
        submitted=_optional_bool(record.get("submitted"), "submitted", line_number),
        place_attempted=_optional_bool(
            record.get("place_attempted"), "place_attempted", line_number
        ),
        payload=canonical,
    )


def _required_text(record: dict[object, object], key: str, line: int) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"shadow ledger line {line} requires non-empty {key}")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_bool(value: object, field: str, line: int) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"shadow ledger line {line} has non-boolean {field}")


def _observed_at(value: str, line: int) -> datetime | None:
    if value == "session_start":
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"shadow ledger line {line} has invalid feed_ts") from exc
    if observed.utcoffset() is None:
        raise ValueError(f"shadow ledger line {line} feed_ts must be timezone-aware")
    return observed


def _count(connection: duckdb.DuckDBPyConnection, relation: str) -> int:
    allowed = {
        "shadow_ledger_events",
        "shadow_regime_observations",
        "shadow_completed_5m_bars",
    }
    if relation not in allowed:
        raise ValueError(f"unsupported shadow relation: {relation}")
    row = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise RuntimeError(f"invalid row count for {relation}")
    return row[0]
