#!/usr/bin/env python3
"""Run one immutable report-only Apex-derived cohort research pass."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from hypervector.research.apex_cohort_contract import (
    APEX_CANDIDATES,
    RESEARCH_SEGMENTS,
    ApexCohortContract,
)
from hypervector.research.apex_cohort_evaluation import (
    ApexScreenRequest,
    run_apex_candidate,
)


_SCHEMA_VERSION = "apex_cohort_screen_v1"


def _parser() -> argparse.ArgumentParser:
    """Build the explicit bounded research command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        required=True,
        choices=tuple(candidate.name for candidate in APEX_CANDIDATES),
    )
    parser.add_argument(
        "--segment",
        required=True,
        choices=tuple(segment.name for segment in RESEARCH_SEGMENTS),
    )
    parser.add_argument("--symbol", required=True, choices=("BTC", "SOL"))
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--funding", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one frozen pass and retain every completed result."""
    args = _parser().parse_args(argv)
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(f"Apex cohort output exists: {output}")
    request = _validated_request(args)
    result = run_apex_candidate(request)
    payload = _report(request, result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote report-only Apex cohort artifact: {output}")
    return 0


def _validated_request(args: argparse.Namespace) -> ApexScreenRequest:
    """Resolve and validate a request against the frozen cohort contract."""
    start = _timestamp(str(args.start))
    end = _timestamp(str(args.end))
    segment = next(item for item in RESEARCH_SEGMENTS if item.name == str(args.segment))
    if start != segment.start_utc or end != segment.end_utc:
        raise ValueError(
            f"request must match frozen {segment.name} window: "
            f"{segment.start_utc.isoformat()} to {segment.end_utc.isoformat()}"
        )
    database = Path(args.database)
    if not database.is_file():
        raise FileNotFoundError(f"research database does not exist: {database}")
    funding = Path(args.funding)
    if not funding.is_file():
        raise FileNotFoundError(f"funding evidence does not exist: {funding}")
    return ApexScreenRequest(
        str(args.candidate),
        segment.name,
        str(args.symbol),
        start,
        end,
        database,
        funding,
    )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Apex cohort timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _report(
    request: ApexScreenRequest,
    result: dict[str, object],
) -> dict[str, object]:
    contract = ApexCohortContract()
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "candidate": request.candidate,
        "segment": request.segment,
        "symbol": request.symbol,
        "start_utc": request.start_utc.isoformat(),
        "end_utc": request.end_utc.isoformat(),
        "report_only": contract.report_only,
        "execution_authority": contract.execution_authority,
        "place_attempted": contract.place_attempted,
        "assumptions": asdict(contract),
        "input_identity": {
            **_database_identity(request.database_path),
            "funding_path": str(request.funding_path.resolve()),
            "funding_sha256": _file_sha256(request.funding_path),
        },
        "result": result,
    }


def _database_identity(path: Path) -> dict[str, object]:
    """Fingerprint stable file metadata without hashing a multi-gigabyte database."""
    stat = path.stat()
    identity = f"{path.resolve()}\x1f{stat.st_size}\x1f{stat.st_mtime_ns}"
    return {
        "database_path": str(path.resolve()),
        "database_size_bytes": stat.st_size,
        "database_mtime_ns": stat.st_mtime_ns,
        "database_metadata_sha256": sha256(identity.encode()).hexdigest(),
        "fingerprint_scope": "resolved_path_size_mtime_not_full_file_content",
    }


def _file_sha256(path: Path) -> str:
    """Hash one bounded immutable input artifact."""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
