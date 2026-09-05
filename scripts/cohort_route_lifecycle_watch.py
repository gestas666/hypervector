#!/usr/bin/env python3
"""Watch one exact cohort route for resolved long and short lifecycles."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_route_lifecycle_evidence import (
    RouteLifecycleBoundary,
    RouteLifecycleIdentity,
    build_route_lifecycle_status,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

Record = Mapping[str, object]
_TRANSIENT_CHECKPOINT_ERRORS = frozenset(
    {
        "checkpoint is stale for route lifecycle evidence",
        "route lifecycle tracker requires a consistent live runtime",
    }
)
_TRANSIENT_RETRY_SECONDS = 15.0


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable route lifecycle watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
    )
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--final-out", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-fingerprint", required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--signal-strategy-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--required-side", action="append", choices=("long", "short"), required=True
    )
    parser.add_argument("--maximum-checkpoint-age-seconds", type=float, default=180.0)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def capture_once(args: argparse.Namespace) -> dict[str, object]:
    """Publish one exact mutable progress status and optional final artifact."""
    identity = _identity(args)
    boundary, preregistration, generators = _preregistration(
        args.preregistration, identity
    )
    if args.final_out.is_file():
        final = _validated_final(args.final_out, identity, preregistration, generators)
        status = _already_complete(final, args.final_out)
        write_atomic_json(args.status, status)
        return status
    checkpoint, evidence = _checkpoint(args.checkpoint)
    status = build_route_lifecycle_status(
        checkpoint,
        identity,
        boundary=boundary,
        observed_at=datetime.now(UTC),
        maximum_checkpoint_age_seconds=args.maximum_checkpoint_age_seconds,
    )
    status["preregistration_evidence"] = preregistration
    status["generator_identity"] = generators
    if status["minimum_diagnostic_evidence_met"] is True:
        _recheck_preregistration(
            args.preregistration,
            identity,
            boundary,
            preregistration,
            generators,
        )
        final = _final_payload(status, evidence, preregistration, generators)
        write_immutable_json(args.final_out, final)
        status = {**status, "final_artifact": _path_evidence(args.final_out)}
    write_atomic_json(args.status, status)
    return status


def run_watcher(
    args: argparse.Namespace,
    *,
    sleep_fn: object = time.sleep,
) -> int:
    """Poll until complete, once requested, or a cycle bound is reached."""
    _validate_loop_args(args)
    sleeper = sleep_fn
    if not callable(sleeper):
        raise TypeError("sleep function must be callable")
    cycles = 0
    while True:
        try:
            status = capture_once(args)
        except ValueError as exc:
            if args.once or str(exc) not in _TRANSIENT_CHECKPOINT_ERRORS:
                raise
            sleeper(min(args.interval_seconds, _TRANSIENT_RETRY_SECONDS))
            continue
        cycles += 1
        if status["state"] in {"diagnostic_minimum_complete", "already_complete"}:
            return 0
        if args.once or (args.max_cycles and cycles >= args.max_cycles):
            return 0
        sleeper(args.interval_seconds)


def _identity(args: argparse.Namespace) -> RouteLifecycleIdentity:
    return RouteLifecycleIdentity(
        run_id=args.run_id,
        profile_id=args.profile_id,
        profile_fingerprint=args.profile_fingerprint,
        provider_id=args.provider_id,
        signal_strategy_id=args.signal_strategy_id,
        symbol=args.symbol,
        required_sides=tuple(args.required_side),
    )


def _checkpoint(path: Path) -> tuple[Record, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"route lifecycle checkpoint is missing: {path}")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "route lifecycle checkpoint")
    evidence = {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }
    return payload, evidence


def _final_payload(
    status: Record,
    checkpoint_evidence: Record,
    preregistration: Record,
    generators: Sequence[Record],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_final",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "contract": dict(_mapping(status.get("contract"), "status contract")),
        "identity": dict(_mapping(status.get("identity"), "status identity")),
        "source_evidence": {
            "checkpoint": dict(checkpoint_evidence),
            "preregistration": dict(preregistration),
        },
        "generator_identity": [dict(row) for row in generators],
        "result": dict(status),
    }


def _validated_final(
    path: Path,
    identity: RouteLifecycleIdentity,
    preregistration: Record,
    generators: Sequence[Record],
) -> Record:
    final = _mapping(json.loads(path.read_text()), "route lifecycle final")
    if final.get("schema_version") != 1:
        raise ValueError("route lifecycle final schema is invalid")
    if final.get("mode") != "cohort_exact_route_lifecycle_final":
        raise ValueError("route lifecycle final mode is invalid")
    contract = _mapping(final.get("contract"), "route lifecycle final contract")
    if contract.get("execution_authority") != "none":
        raise ValueError("route lifecycle final has execution authority")
    expected = _identity_payload(identity)
    if _mapping(final.get("identity"), "route lifecycle final identity") != expected:
        raise ValueError("route lifecycle final identity mismatch")
    result = _mapping(final.get("result"), "route lifecycle final result")
    if result.get("minimum_diagnostic_evidence_met") is not True:
        raise ValueError("route lifecycle final is not complete")
    sources = _mapping(final.get("source_evidence"), "route lifecycle sources")
    if sources.get("preregistration") != preregistration:
        raise ValueError("route lifecycle final preregistration mismatch")
    if final.get("generator_identity") != [dict(row) for row in generators]:
        raise ValueError("route lifecycle final generator identity mismatch")
    return final


def _preregistration(
    path: Path, identity: RouteLifecycleIdentity
) -> tuple[RouteLifecycleBoundary, dict[str, object], list[dict[str, object]]]:
    payload, evidence = _json_evidence(path, "route lifecycle preregistration")
    if payload.get("schema_version") != 1:
        raise ValueError("route lifecycle preregistration schema is invalid")
    if payload.get("mode") != "v57_exact_route_lifecycle_tracker_preregistration":
        raise ValueError("route lifecycle preregistration mode is invalid")
    if _mapping(payload.get("live_identity"), "preregistered identity") != (
        _identity_payload(identity)
    ):
        raise ValueError("route lifecycle preregistration identity mismatch")
    _report_only_contract(payload.get("contract"), "preregistration")
    boundary = _boundary(payload)
    generators = _generator_identity(payload)
    return boundary, evidence, generators


def _recheck_preregistration(
    path: Path,
    identity: RouteLifecycleIdentity,
    boundary: RouteLifecycleBoundary,
    evidence: Record,
    generators: Sequence[Record],
) -> None:
    observed = _preregistration(path, identity)
    expected = (boundary, dict(evidence), [dict(row) for row in generators])
    if observed != expected:
        raise ValueError("route lifecycle preregistration changed during poll")


def _boundary(payload: Record) -> RouteLifecycleBoundary:
    row = _mapping(payload.get("prospective_boundary"), "prospective boundary")
    return RouteLifecycleBoundary(
        capture_start_ms=_integer(row.get("capture_start_ms"), "capture start"),
        baseline_evaluations=_integer(
            row.get("baseline_route_evaluations"), "baseline route evaluations"
        ),
        baseline_eligible=_integer(
            row.get("baseline_eligible_evaluations"), "baseline eligible evaluations"
        ),
    )


def _generator_identity(payload: Record) -> list[dict[str, object]]:
    rows = payload.get("implementation_evidence")
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence) or not rows:
        raise ValueError("implementation evidence must be a non-empty array")
    output = [_verified_file(_mapping(row, "generator evidence")) for row in rows]
    paths = [row["path"] for row in output]
    if len(paths) != len(set(paths)):
        raise ValueError("generator evidence paths must be unique")
    return output


def _verified_file(expected: Record) -> dict[str, object]:
    path = Path(_text(expected.get("path"), "generator evidence path"))
    raw = path.read_bytes()
    observed = {"path": str(path), "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
    if observed != dict(expected):
        raise ValueError(f"generator evidence changed: {path}")
    return observed


def _json_evidence(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), label)
    return payload, {
        "path": str(path),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def _report_only_contract(value: object, label: str) -> None:
    contract = _mapping(value, f"{label} contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(field) != target for field, target in expected.items()):
        raise ValueError(f"{label} contract is not report-only")


def _already_complete(final: Record, path: Path) -> dict[str, object]:
    result = dict(_mapping(final.get("result"), "route lifecycle final result"))
    result["state"] = "already_complete"
    result["final_artifact"] = _path_evidence(path)
    return result


def _identity_payload(identity: RouteLifecycleIdentity) -> dict[str, object]:
    return {
        "run_id": identity.run_id,
        "profile_id": identity.profile_id,
        "profile_fingerprint": identity.profile_fingerprint,
        "provider_id": identity.provider_id,
        "signal_strategy_id": identity.signal_strategy_id,
        "symbol": identity.symbol,
        "route": identity.route,
        "required_sides": list(identity.required_sides),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def _validate_loop_args(args: argparse.Namespace) -> None:
    for value, label in (
        (args.interval_seconds, "interval seconds"),
        (args.maximum_checkpoint_age_seconds, "maximum checkpoint age"),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be finite")
        if value <= 0.0:
            raise ValueError(f"{label} must be positive")
    if (
        isinstance(args.max_cycles, bool)
        or not isinstance(args.max_cycles, int)
        or args.max_cycles < 0
    ):
        raise ValueError("max cycles must be a nonnegative integer")
    _identity(args)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only watcher under a singleton status lock."""
    try:
        args = build_parser().parse_args(argv)
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(f"route lifecycle watcher refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
