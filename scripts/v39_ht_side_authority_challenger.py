#!/usr/bin/env python3
"""Freeze exact v39 HT side-authority variants without execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.data.reporting_duckdb import connect_reporting_database
from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
)
from hypervector.research.v39_ht_side_authority_challenger import (
    build_v39_ht_side_authority_challenger,
)

Record = Mapping[str, object]
RowLoader = Callable[[Path, str], tuple[dict[str, object], ...]]
_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_DEFAULT_OUTPUT = Path(
    f"data/logs/research/bidirectional_cohort/"
    f"v39_ht_side_authority_challenger_{_STAMP}.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/research/market.duckdb")
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    row_loader: RowLoader | None = None,
) -> dict[str, object]:
    """Read an exact durable v39 prefix and publish frozen side decisions."""
    database = Path(args.database)
    run_id = str(args.run_id)
    rows = (row_loader or _load_rows)(database, run_id)
    _require_exact_profile(rows)
    evaluations = _evaluations(rows)
    report = build_v39_ht_side_authority_challenger(
        evaluations,
        run_id=run_id,
        profile_fingerprint=PROFILE_FINGERPRINT,
    )
    source = report["source"]
    if not isinstance(source, dict):
        raise RuntimeError("v39 HT challenger source must be mutable")
    source.update(_source_evidence(database, rows))
    report["generator_identity"] = _generator_identity()
    write_immutable_json(Path(args.output), report)
    return report


def _load_rows(database: Path, run_id: str) -> tuple[dict[str, object], ...]:
    if not database.is_file():
        raise FileNotFoundError(f"cohort research database is missing: {database}")
    query = """
        SELECT profile_id, profile_fingerprint,
               CAST(observed_at_utc AS VARCHAR), sequence, CAST(payload AS VARCHAR)
        FROM cohort_live_events
        WHERE run_id = ? AND event_type = 'intent_routing'
        ORDER BY observed_at_utc, sequence
    """
    with connect_reporting_database(database, read_only=True) as connection:
        values = connection.execute(query, [run_id]).fetchall()
    return tuple(_row(value) for value in values)


def _row(value: tuple[object, ...]) -> dict[str, object]:
    if len(value) != 5:
        raise ValueError("v39 HT routing query returned an invalid row")
    payload = json.loads(str(value[4]))
    if not isinstance(payload, dict):
        raise ValueError("v39 HT routing payload must be an object")
    return {
        "profile_id": value[0],
        "profile_fingerprint": value[1],
        "observed_at_utc": str(value[2]),
        "sequence": value[3],
        "payload": payload,
    }


def _evaluations(rows: tuple[dict[str, object], ...]) -> tuple[Record, ...]:
    output: list[Record] = []
    for row in rows:
        payload = _mapping(row.get("payload"), "routing payload")
        values = payload.get("evaluations")
        if not isinstance(values, list) or not all(
            isinstance(item, Mapping) for item in values
        ):
            raise ValueError("routing evaluations must be an array of objects")
        output.extend(values)
    return tuple(output)


def _require_exact_profile(rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError("exact v39 run has no durable intent-routing rows")
    identities = {
        (row.get("profile_id"), row.get("profile_fingerprint")) for row in rows
    }
    if identities != {(PROFILE_ID, PROFILE_FINGERPRINT)}:
        raise ValueError("intent-routing rows do not match exact v39 profile identity")


def _source_evidence(
    database: Path, rows: tuple[dict[str, object], ...]
) -> dict[str, object]:
    observed = tuple(_utc_text(row["observed_at_utc"]) for row in rows)
    sequences = tuple(_integer(row.get("sequence"), "routing sequence") for row in rows)
    return {
        "database_path": str(database.resolve()),
        "routing_events": len(rows),
        "first_observed_at_utc": min(observed),
        "last_observed_at_utc": max(observed),
        "first_sequence": min(sequences),
        "last_sequence": max(sequences),
    }


def _utc_text(value: object) -> str:
    timestamp = datetime.fromisoformat(str(value).replace(" ", "T"))
    if timestamp.tzinfo is None:
        raise ValueError("routing observation timestamp must include a timezone")
    return timestamp.astimezone(UTC).isoformat()


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/v39_ht_side_authority_challenger.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def main() -> int:
    """Run the exact report-only challenger and print a compact summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "summary": report["summary"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
