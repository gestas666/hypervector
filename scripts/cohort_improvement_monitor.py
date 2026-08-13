#!/usr/bin/env python3
"""Continuously publish a bounded report-only portfolio improvement digest."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_improvement_digest import (
    build_cohort_improvement_digest,
)
from hypervector.research.cohort_improvement_history import append_material_report
from hypervector.research.cohort_continuous_improvement import (
    build_continuous_improvement_report,
)
from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]
SleepFn = Callable[[float], None]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_improvement_digest.json")
_HISTORY = Path("data/live/research/v51_continuous_improvement.jsonl")
_MAXIMUM_CHECKPOINT_AGE_SECONDS = 180.0
_DECISION_OVERRIDES = Path(
    "configs/research/cohort_improvement_decision_overrides_v51.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable improvement-monitor parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--history", type=Path, default=_HISTORY)
    parser.add_argument(
        "--decision-overrides",
        type=Path,
        default=_DECISION_OVERRIDES,
    )
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument(
        "--maximum-checkpoint-age-seconds",
        type=float,
        default=_MAXIMUM_CHECKPOINT_AGE_SECONDS,
    )
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def refresh(args: argparse.Namespace) -> dict[str, object]:
    """Build and atomically publish one source-bound digest."""
    raw = args.checkpoint.read_bytes()
    checkpoint = _mapping(json.loads(raw), "improvement checkpoint")
    _validate_checkpoint(checkpoint)
    _validate_checkpoint_freshness(
        checkpoint,
        datetime.now(UTC),
        args.maximum_checkpoint_age_seconds,
    )
    audit = _mapping(checkpoint.get("audit"), "improvement checkpoint audit")
    overrides, override_raw = _load_decision_overrides(args.decision_overrides)
    _validate_override_identity(overrides, audit)
    digest = build_cohort_improvement_digest(
        audit,
        experiment_overrides=overrides,
    )
    report = build_continuous_improvement_report(checkpoint, digest)
    material_hash = _material_digest(report)
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "source_checkpoint_generated_at_utc": _text(
                checkpoint.get("generated_at_utc"), "checkpoint generation time"
            ),
            "material_state_sha256": material_hash,
            "evidence": {
                "checkpoint": {
                    "path": str(args.checkpoint.resolve()),
                    "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
                "decision_overrides": {
                    "path": str(args.decision_overrides.resolve()),
                    "sha256": sha256(override_raw).hexdigest(),
                    "bytes": len(override_raw),
                },
            },
        }
    )
    write_atomic_json(args.out, report)
    append_material_report(args.history, report)
    return report


def _load_decision_overrides(path: Path) -> tuple[Record, bytes]:
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "research decision overrides")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("research decision override evidence must be an array")
    for index, item in enumerate(evidence):
        record = _mapping(item, f"research decision evidence {index}")
        relative = _text(record.get("path"), "research decision evidence path")
        evidence_path = (path.parent / relative).resolve()
        actual = file_evidence(evidence_path)
        if any(record.get(field) != actual[field] for field in ("sha256", "bytes")):
            raise ValueError(f"research decision evidence mismatch: {evidence_path}")
    return payload, raw


def run_monitor(args: argparse.Namespace, *, sleep_fn: SleepFn = time.sleep) -> int:
    """Refresh until stopped while retaining the last valid output on failure."""
    _validate_loop_args(args)
    completed = 0
    while True:
        try:
            report = refresh(args)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            _emit_failure(exc)
            if args.once:
                return 2
        else:
            completed += 1
            _emit_success(report)
            if args.once or (args.max_cycles and completed >= args.max_cycles):
                return 0
        sleep_fn(args.interval_seconds)


def _validate_checkpoint(checkpoint: Record) -> None:
    contract = _mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if contract.get(field) != value:
            raise ValueError(f"improvement checkpoint has invalid {field}")


def _validate_override_identity(overrides: Record, audit: Record) -> None:
    run = _mapping(audit.get("run"), "improvement audit run")
    expected = (
        ("source_profile_id", "profile_id"),
        ("source_profile_fingerprint", "profile_fingerprint"),
    )
    mismatches = [
        source
        for source, target in expected
        if _text(overrides.get(source), source) != _text(run.get(target), target)
    ]
    if mismatches:
        raise ValueError(f"decision override profile identity mismatch: {mismatches}")


def _validate_checkpoint_freshness(
    checkpoint: Record,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> None:
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("maximum checkpoint age must be positive and finite")
    generated_at = _timestamp(
        checkpoint.get("generated_at_utc"), "checkpoint generation time"
    )
    age = (observed_at - generated_at).total_seconds()
    if age < 0.0:
        raise ValueError("checkpoint generation time is in the future")
    if age > maximum_age_seconds:
        raise ValueError(
            f"checkpoint is stale: age={age:.3f}s limit={maximum_age_seconds:.3f}s"
        )


def _validate_loop_args(args: argparse.Namespace) -> None:
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0.0:
        raise ValueError("improvement monitor interval must be positive and finite")
    if args.max_cycles < 0:
        raise ValueError("improvement monitor max cycles cannot be negative")
    if (
        not math.isfinite(args.maximum_checkpoint_age_seconds)
        or args.maximum_checkpoint_age_seconds <= 0.0
    ):
        raise ValueError("maximum checkpoint age must be positive and finite")


def _emit_success(report: Record) -> None:
    assessment = _mapping(report.get("assessment"), "improvement assessment")
    performance = _mapping(report.get("performance"), "improvement performance")
    print(
        json.dumps(
            {
                "event": "cohort_improvement_digest",
                "state": "published",
                "closed_trades": performance.get("closed_trades"),
                "top_research_priority": assessment.get("top_research_priority"),
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
                "event": "cohort_improvement_digest",
                "state": "unavailable",
                "technical_issue": f"{type(exc).__name__}: {exc}",
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _material_digest(value: Record) -> str:
    material = json.loads(json.dumps(value))
    source = material.get("source")
    if isinstance(source, dict):
        source.pop("last_observed_at_utc", None)
    operational = material.get("operational_assessment")
    if isinstance(operational, dict):
        operational.pop("heartbeat_age_seconds", None)
    evidence_health = material.get("evidence_health")
    if isinstance(evidence_health, dict):
        evidence_health.pop("right_censored_observations", None)
        evidence_health.pop("metric_value_gaps", None)
    _normalize_live_diagnostic_material(material)
    return _digest(material)


def _normalize_live_diagnostic_material(material: dict[str, object]) -> None:
    diagnostics = material.get("live_opportunity_diagnostics")
    if not isinstance(diagnostics, dict):
        return
    window = diagnostics.get("observation_window")
    if isinstance(window, dict):
        window.pop("end_utc", None)
        window.pop("duration_seconds", None)
    totals = diagnostics.get("totals")
    if isinstance(totals, dict):
        totals.pop("evaluations", None)
        totals.pop("directional_evaluations", None)
        totals.pop("right_censored_observations", None)
    routes = diagnostics.get("routes")
    if not isinstance(routes, list):
        return
    for route in routes:
        if not isinstance(route, dict):
            continue
        for field in (
            "outcome_evaluations",
            "readiness_evaluations",
            "latest_readiness_fraction",
            "latest_blockers",
            "blocker_counts",
        ):
            route.pop(field, None)
        paths = route.get("one_blocker_paths")
        if isinstance(paths, list):
            for path in paths:
                if isinstance(path, dict):
                    _normalize_path_material(path)
    leads = diagnostics.get("robust_report_only_leads")
    if isinstance(leads, list):
        for lead in leads:
            if isinstance(lead, dict):
                _normalize_path_material(lead)


def _normalize_path_material(path: dict[str, object]) -> None:
    path.pop("blocker_evaluations", None)
    path.pop("censored", None)


def _digest(value: Record) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only portfolio improvement monitor."""
    return run_monitor(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
