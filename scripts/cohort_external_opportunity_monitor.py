#!/usr/bin/env python3
"""Publish a continuous report-only external-candidate opportunity pipeline."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_external_opportunity_pipeline import (
    ExternalOpportunityPaths,
    load_brentoil_external_opportunity,
)

NowFn = Callable[[], datetime]
SleepFn = Callable[[float], None]

_CANARY = Path(
    "data/logs/research/bidirectional_cohort/"
    "brentoil_live_canary_lifecycle_reconciliation_20260815_v1.json"
)
_DEVELOPMENT = Path(
    "data/logs/research/xyz_brentoil_oil_shock_reversion_development_20260815_v4.json"
)
_PARITY_DIRECTORY = Path("data/logs/research")
_PARITY_PATTERN = "xyz_brentoil_oil_shock_candle_parity_*.json"
_OBSERVER = Path("data/runtime/research/brentoil_oil_shock_shadow_v2_latest.json")
_OUTPUT = Path("data/runtime/research/latest_external_opportunity_pipeline.json")
_STATUS = Path("data/runtime/research/latest_external_opportunity_pipeline_status.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable external-opportunity parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", type=Path, default=_CANARY)
    parser.add_argument("--development", type=Path, default=_DEVELOPMENT)
    parser.add_argument("--parity", type=Path)
    parser.add_argument("--observer", type=Path, default=_OBSERVER)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--maximum-observer-age-seconds", type=float, default=360.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def refresh(args: argparse.Namespace, *, observed_at: datetime) -> dict[str, object]:
    """Build and atomically publish one external-opportunity assessment."""
    paths = _paths(args)
    _validate_distinct_paths(paths, args.out, args.status)
    report, evidence = load_brentoil_external_opportunity(
        paths,
        observed_at=observed_at,
        maximum_observer_age_seconds=args.maximum_observer_age_seconds,
    )
    report.update(
        {
            "generated_at_utc": observed_at.astimezone(UTC).isoformat(),
            "evidence": evidence,
        }
    )
    write_atomic_json(args.out, report)
    _write_health(args.status, args.out, observed_at, technical_issue=None)
    return report


def run_monitor(
    args: argparse.Namespace,
    *,
    now_fn: NowFn = lambda: datetime.now(UTC),
    sleep_fn: SleepFn = time.sleep,
) -> int:
    """Refresh until stopped while preserving the last valid report on failure."""
    _validate_loop_args(args)
    _validate_distinct_paths(_paths(args), args.out, args.status)
    completed = 0
    while True:
        try:
            report = refresh(args, observed_at=now_fn())
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            observed_at = now_fn()
            _write_health(
                args.status,
                args.out,
                observed_at,
                technical_issue=f"{type(exc).__name__}: {exc}",
            )
            _emit_failure(exc)
            if args.once:
                return 2
        else:
            completed += 1
            _emit_success(report)
            if args.once or (args.max_cycles and completed >= args.max_cycles):
                return 0
        sleep_fn(args.interval_seconds)


def _paths(args: argparse.Namespace) -> ExternalOpportunityPaths:
    return ExternalOpportunityPaths(
        canary=args.canary,
        development=args.development,
        parity=args.parity or latest_brentoil_parity_path(_PARITY_DIRECTORY),
        observer=args.observer,
    )


def latest_brentoil_parity_path(directory: Path) -> Path:
    """Return the newest valid BRENTOIL parity artifact by observation time."""
    candidates: list[tuple[int, Path]] = []
    for path in directory.glob(_PARITY_PATTERN):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        scope = payload.get("scope")
        contract = payload.get("contract")
        if not isinstance(scope, dict) or not isinstance(contract, dict):
            continue
        observed = scope.get("observed_at_ms")
        valid = (
            payload.get("schema_version") == "hip3_prospective_candle_parity_v1"
            and scope.get("symbol") == "xyz:BRENTOIL"
            and isinstance(observed, int)
            and not isinstance(observed, bool)
            and contract.get("report_only") is True
            and contract.get("execution_authority") == "none"
        )
        if valid:
            candidates.append((observed, path))
    if not candidates:
        raise FileNotFoundError("no valid BRENTOIL candle parity artifact exists")
    return max(candidates, key=lambda item: (item[0], str(item[1])))[1]


def _validate_loop_args(args: argparse.Namespace) -> None:
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0.0:
        raise ValueError("external-opportunity interval must be positive and finite")
    maximum_age = args.maximum_observer_age_seconds
    if not math.isfinite(maximum_age) or maximum_age <= 0.0:
        raise ValueError("external-opportunity maximum age must be positive and finite")
    if args.max_cycles < 0:
        raise ValueError("external-opportunity max cycles cannot be negative")


def _validate_distinct_paths(
    paths: ExternalOpportunityPaths, output: Path, status: Path
) -> None:
    values = {
        paths.canary.resolve(),
        paths.development.resolve(),
        paths.parity.resolve(),
        paths.observer.resolve(),
        output.resolve(),
        status.resolve(),
    }
    if len(values) != 6:
        raise ValueError("external-opportunity input and output paths must be distinct")


def _write_health(
    status: Path,
    output: Path,
    observed_at: datetime,
    *,
    technical_issue: str | None,
) -> None:
    """Publish current monitor health without replacing last valid evidence."""
    write_atomic_json(
        status,
        {
            "schema_version": 1,
            "mode": "external_candidate_opportunity_pipeline_status",
            "state": "available" if technical_issue is None else "unavailable",
            "generated_at_utc": observed_at.astimezone(UTC).isoformat(),
            "technical_issue": technical_issue,
            "last_valid_report_preserved": output.exists(),
            "report": _report_reference(output),
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "automatic_live_change": False,
                "runtime_strategy_changed": False,
            },
        },
    )


def _report_reference(path: Path) -> dict[str, object]:
    """Return the exact last-valid report identity when one exists."""
    if not path.exists():
        return {"path": str(path.resolve()), "exists": False}
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "exists": True,
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _emit_success(report: dict[str, object]) -> None:
    candidates = report.get("candidates")
    count = len(candidates) if isinstance(candidates, list) else 0
    print(
        json.dumps(
            {
                "event": "external_opportunity_pipeline",
                "state": "published",
                "candidates": count,
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _emit_failure(exc: Exception) -> None:
    print(
        json.dumps(
            {
                "event": "external_opportunity_pipeline",
                "state": "unavailable",
                "technical_issue": f"{type(exc).__name__}: {exc}",
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only external-opportunity monitor."""
    return run_monitor(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
