"""Durable all-live performance projection across cohort profile generations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from hypervector.data.reporting_duckdb import connect_reporting_database
from hypervector.research.cohort_live_archive_query import (
    load_archive_lifecycle_rows,
)
from hypervector.research.cohort_trade_performance import (
    build_all_time_trade_performance,
)

_SYMBOL_ORDER = ("BTC", "ETH", "SOL", "HYPE")
PORTFOLIO_ARCHIVE_PROJECTION_REVISION = 2
_PROFILE_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class CohortAccountingEpoch:
    """Profile-and-time boundary for one recoverable reporting epoch."""

    epoch_id: str
    profile_fingerprint: str
    start_venue_timestamp_ms: int

    def __post_init__(self) -> None:
        """Reject an ambiguous or malformed accounting boundary."""
        if not self.epoch_id.strip():
            raise ValueError("accounting epoch id must be non-empty")
        if not _PROFILE_FINGERPRINT.fullmatch(self.profile_fingerprint):
            raise ValueError("accounting epoch profile fingerprint is invalid")
        if (
            isinstance(self.start_venue_timestamp_ms, bool)
            or not isinstance(self.start_venue_timestamp_ms, int)
            or self.start_venue_timestamp_ms < 0
        ):
            raise ValueError("accounting epoch start timestamp is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the exact persisted reporting boundary."""
        return asdict(self)


@dataclass(frozen=True)
class CohortLiveFillIdentity:
    """Exact identity of the append-only raw execution-fill event set."""

    fill_events: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe identity for checkpoint persistence."""
        return asdict(self)


@dataclass(frozen=True)
class CohortLiveArchiveSource:
    """One immutable database projection shared by identity and archive build."""

    database_path: str
    identity: CohortLiveFillIdentity
    lifecycle_rows: tuple[tuple[object, ...], ...]
    observed_through_utc: datetime | None


def cohort_live_fill_identity(database_path: Path) -> CohortLiveFillIdentity:
    """Hash raw fills plus the lifecycle rows that drive the archive."""
    return load_cohort_live_archive_source(database_path).identity


def load_cohort_live_archive_source(
    database_path: Path,
) -> CohortLiveArchiveSource:
    """Load one exact source snapshot for identity and archive construction."""
    if not database_path.is_file():
        raise FileNotFoundError(f"cohort research database not found: {database_path}")
    with connect_reporting_database(database_path, read_only=True) as connection:
        fill_rows = connection.execute(
            """
            SELECT event_id
            FROM cohort_live_events
            WHERE event_type = 'fill'
            ORDER BY event_id
            """
        ).fetchall()
        lifecycle_rows = load_archive_lifecycle_rows(connection)
        observed_through = connection.execute(
            "SELECT max(observed_at_utc) FROM cohort_live_events"
        ).fetchone()
    latest = observed_through[0] if observed_through is not None else None
    if latest is not None and not isinstance(latest, datetime):
        raise ValueError("portfolio archive observation time is invalid")
    return CohortLiveArchiveSource(
        database_path=str(database_path.resolve()),
        identity=_fill_identity(fill_rows, lifecycle_rows),
        lifecycle_rows=tuple(tuple(row) for row in lifecycle_rows),
        observed_through_utc=latest,
    )


def _fill_identity(
    fill_rows: Sequence[Sequence[object]],
    lifecycle_rows: Sequence[Sequence[object]],
) -> CohortLiveFillIdentity:
    digest = hashlib.sha256()
    digest.update(b"cohort-live-fill-identity-v2\n")
    for row in fill_rows:
        event_id = _text(row[0], "fill event identity")
        digest.update(b"fill|")
        digest.update(event_id.encode("ascii") + b"\n")
    for row in lifecycle_rows:
        encoded = json.dumps(
            list(row), allow_nan=False, separators=(",", ":"), ensure_ascii=True
        )
        digest.update(b"lifecycle|")
        digest.update(encoded.encode("ascii") + b"\n")
    return CohortLiveFillIdentity(
        fill_events=len(fill_rows),
        sha256=digest.hexdigest(),
    )


def load_cohort_live_portfolio_archive(
    database_path: Path,
    *,
    source: CohortLiveArchiveSource | None = None,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> dict[str, object]:
    """Load every resolved live lifecycle from the durable research database."""
    active_source = source or load_cohort_live_archive_source(database_path)
    if active_source.database_path != str(database_path.resolve()):
        raise ValueError("portfolio archive source belongs to a different database")
    selected_rows = _epoch_rows(active_source.lifecycle_rows, accounting_epoch)
    trades = tuple(_trade_record(row) for row in selected_rows)
    symbols = _ordered_symbols(trades)
    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "projection_revision": PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
        "source_execution": active_source.identity.to_dict(),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "performance_gate": False,
            "balance_gate": False,
        },
        "symbols": list(symbols),
        "observed_through_utc": _timestamp_text(active_source.observed_through_utc),
        "coverage": {
            "complete": True,
            "closed_orders": len(trades),
            "leverage_matches": len(trades),
        },
        "performance": build_all_time_trade_performance(trades),
    }
    if accounting_epoch is not None:
        result["accounting_epoch"] = accounting_epoch.to_dict()
    return result


def _epoch_rows(
    rows: Sequence[Sequence[object]],
    epoch: CohortAccountingEpoch | None,
) -> tuple[Sequence[object], ...]:
    if epoch is None:
        return tuple(rows)
    return tuple(
        row
        for row in rows
        if len(row) == 12
        and row[9] == epoch.profile_fingerprint
        and _nonnegative_integer(row[11], "archive exit timestamp")
        >= epoch.start_venue_timestamp_ms
    )


def _trade_record(row: Sequence[object]) -> dict[str, object]:
    if len(row) != 12:
        raise ValueError("portfolio archive query returned an unexpected row shape")
    symbol = _text(row[0], "archive symbol")
    strategy = _text(row[1], "archive strategy")
    run_id = _text(row[2], "archive entry run")
    side = _side(row[3])
    net_pnl = _number(row[4], "archive net PnL")
    fees = _nonnegative(row[5], "archive fees")
    funding = _number(row[6], "archive funding")
    margin = _positive(row[7], "archive entry margin")
    _positive(row[8], "archive leverage")
    profile = _text(row[9], "archive profile fingerprint")
    _positive(row[10], "archive entry order identity")
    exit_timestamp = _nonnegative_integer(row[11], "archive exit timestamp")
    return {
        "strategy_id": strategy,
        "symbol": symbol,
        "side": side,
        "source_run_id": run_id,
        "source_profile_fingerprint": profile,
        "net_pnl_usd": net_pnl,
        "entry_margin_used_usd": margin,
        "net_return_on_margin_pct": net_pnl / margin * 100.0,
        "fees_usd": fees,
        "funding_usd": funding,
        "exit_venue_timestamp_ms": exit_timestamp,
    }


def _ordered_symbols(trades: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    present = {_text(trade.get("symbol"), "archive symbol") for trade in trades}
    ordered = [symbol for symbol in _SYMBOL_ORDER if symbol in present]
    ordered.extend(sorted(present.difference(_SYMBOL_ORDER)))
    return tuple(ordered)


def _side(value: object) -> str:
    direction = _text(value, "archive entry direction")
    if direction == "Open Long":
        return "long"
    if direction == "Open Short":
        return "short"
    raise ValueError(f"unsupported archive entry direction: {direction}")


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("portfolio archive timestamp must be timezone-aware")
    return value.isoformat()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative(value: object, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
