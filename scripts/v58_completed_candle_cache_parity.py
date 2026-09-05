"""Publish bounded V58 live-versus-cached-observer candle parity."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from hypervector.data.jsonl_prefix import read_jsonl_prefix
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v58_completed_candle_cache_parity import (
    build_v58_completed_candle_cache_parity,
)

Record = dict[str, object]

_DEFAULT_DATABASE = Path("data/research/market.duckdb")
_DEFAULT_OBSERVER = Path(
    "data/observe/v58_eight_asset_prospective_20260819_v1/decisions.jsonl"
)
_DEFAULT_OUTPUT = Path(
    "data/runtime/research/v58_completed_candle_cache_parity_latest.json"
)
_QUERY = """
SELECT sequence, observed_at_utc, execution_mode, live_armed,
       execution_authority, profile_id, profile_fingerprint,
       run_fingerprint, run_id, event_type, payload
FROM cohort_live_events
WHERE run_id = ? AND event_type = 'market_candles'
ORDER BY sequence
"""
_COLUMNS = (
    "sequence",
    "observed_at_utc",
    "execution_mode",
    "live_armed",
    "execution_authority",
    "profile_id",
    "profile_fingerprint",
    "run_fingerprint",
    "run_id",
    "event_type",
    "payload",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded report-only command interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-database", type=Path, default=_DEFAULT_DATABASE)
    parser.add_argument("--live-run-id", required=True)
    parser.add_argument("--observer-ledger", type=Path, default=_DEFAULT_OBSERVER)
    parser.add_argument("--observer-run-id", required=True)
    parser.add_argument("--prospective-start-ms", type=int, required=True)
    parser.add_argument("--minimum-contiguous-minutes", type=int, default=1_440)
    parser.add_argument("--maximum-database-age-seconds", type=float, default=300.0)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    return parser


def run(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    """Query immutable row identities and atomically publish exact parity."""
    generated = _aware_utc(now or datetime.now(UTC), "generation time")
    live_rows, live_evidence = _load_live_rows(args.research_database, args.live_run_id)
    _require_fresh_query(
        live_evidence,
        generated,
        args.maximum_database_age_seconds,
    )
    observer_rows, observer_evidence = read_jsonl_prefix(
        args.observer_ledger, "V58 cached observer ledger"
    )
    report = build_v58_completed_candle_cache_parity(
        live_rows=live_rows,
        observer_rows=observer_rows,
        live_run_id=args.live_run_id,
        observer_run_id=args.observer_run_id,
        prospective_start_ms=args.prospective_start_ms,
        minimum_contiguous_minutes=args.minimum_contiguous_minutes,
        generated_at_utc=generated.isoformat(),
    )
    report["evidence"] = {
        "live_database_query": live_evidence,
        "observer_ledger": observer_evidence,
    }
    write_atomic_json(args.out, report)
    _print_summary(args.out, report)
    return 0


def _load_live_rows(
    database: Path, run_id: str
) -> tuple[list[Record], dict[str, object]]:
    if not database.is_file():
        raise FileNotFoundError(f"research database is missing: {database}")
    selected_run = _text(run_id, "live run ID")
    connection = duckdb.connect(str(database), read_only=True)
    try:
        raw_rows = connection.execute(_QUERY, [selected_run]).fetchall()
    finally:
        connection.close()
    rows = [_query_row(values) for values in raw_rows]
    if not rows:
        raise ValueError("live database query returned no market candles")
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    observed = [str(row["observed_at_utc"]) for row in rows]
    stat = database.stat()
    return rows, {
        "path": str(database.resolve()),
        "database_bytes": stat.st_size,
        "database_modified_at_utc": datetime.fromtimestamp(
            stat.st_mtime, tz=UTC
        ).isoformat(),
        "query": "selected_run_market_candles_ordered_by_sequence",
        "run_id": selected_run,
        "rows": len(rows),
        "first_sequence": rows[0]["sequence"],
        "last_sequence": rows[-1]["sequence"],
        "first_observed_at_utc": min(observed),
        "last_observed_at_utc": max(observed),
        "sha256": sha256(canonical).hexdigest(),
    }


def _query_row(values: Sequence[object]) -> Record:
    if len(values) != len(_COLUMNS):
        raise ValueError("live database query returned an invalid row shape")
    row = dict(zip(_COLUMNS, values, strict=True))
    row["observed_at_utc"] = _iso_timestamp(
        row["observed_at_utc"], "database observed time"
    )
    row["payload"] = _payload(row["payload"])
    return row


def _payload(value: object) -> Mapping[str, object]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, Mapping):
        raise ValueError("database candle payload must be an object")
    return decoded


def _require_fresh_query(
    evidence: Mapping[str, object], now: datetime, maximum_age_seconds: object
) -> None:
    maximum = _positive_number(maximum_age_seconds, "maximum database age")
    observed = _parse_timestamp(
        evidence.get("last_observed_at_utc"), "database last observed time"
    )
    age = (now - observed).total_seconds()
    if age < -5.0:
        raise ValueError("database query timestamp is unexpectedly in the future")
    if age > maximum:
        raise ValueError(
            f"database query is stale: age {age:.3f}s exceeds {maximum:.3f}s"
        )


def _print_summary(path: Path, report: Mapping[str, object]) -> None:
    coverage = _mapping(report.get("coverage"), "parity coverage")
    comparison = _mapping(report.get("comparison"), "parity comparison")
    print(
        json.dumps(
            {
                "output": str(path),
                "gate_status": coverage.get("gate_status"),
                "contiguous_exact_minutes": coverage.get("contiguous_exact_minutes"),
                "exact_ohlcv_rows": comparison.get("exact_ohlcv_rows"),
                "mismatches": len(_list(comparison.get("mismatches"), "mismatches")),
            },
            sort_keys=True,
        )
    )


def _iso_timestamp(value: object, label: str) -> str:
    if isinstance(value, datetime):
        return _aware_utc(value, label).isoformat()
    return _parse_timestamp(value, label).isoformat()


def _parse_timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    return _aware_utc(datetime.fromisoformat(text.replace("Z", "+00:00")), label)


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    """Run the V58 parity command."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
