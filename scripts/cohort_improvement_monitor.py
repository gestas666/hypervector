#!/usr/bin/env python3
"""Continuously publish a bounded report-only portfolio improvement digest."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import time

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_improvement_digest import (
    build_cohort_improvement_digest,
)
from hypervector.research.cohort_improvement_history import (
    append_material_report,
    material_state_sha256,
)
from hypervector.research.cohort_active_route_lifecycle_status import (
    ActiveRouteLifecycleCollection,
    load_active_route_lifecycle_statuses,
)
from hypervector.research.cohort_improvement_monitor_output import (
    emit_failure as _emit_failure,
    emit_success as _emit_success,
)
from hypervector.research.cohort_hype_native_lifecycle_status import (
    HypeNativeLifecycleEvidence,
    load_hype_native_for_profile,
)
from hypervector.research.cohort_index_signal_capture_health import (
    SignalCaptureHealth,
    load_v51_index_signal_capture_for_audit as _load_index_signals,
)
from hypervector.research.cohort_external_asset_pipeline import (
    ExternalAssetPipeline,
    load_external_asset_pipeline,
)
from hypervector.research.cohort_mark_capture_health import (
    MarkCaptureHealth,
    load_index_mark_capture_health as _load_index_mark_capture,
)
import hypervector.research.cohort_successor_observer_status as v58
from hypervector.research.cohort_prospective_experiment_evidence import (
    ObserverIdentity,
    ProspectiveExperimentEvidence,
    attach_prospective_experiment_evidence,
    load_sol_route_native_observer,
)
from hypervector.research.cohort_cadence_review_clock import (
    build_monitored_improvement_report as build_continuous_improvement_report,
)
from hypervector.research.cohort_improvement_monitor_validation import (
    validate_checkpoint_freshness as _validate_checkpoint_freshness,
    validate_loop_args as _validate_loop_args,
)
from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]
SleepFn = Callable[[float], None]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_improvement_digest.json")
_HISTORY = Path("data/live/research/v51_continuous_improvement.jsonl")
_MAXIMUM_CHECKPOINT_AGE_SECONDS = 180.0
_MAXIMUM_SOL_OBSERVER_AGE_SECONDS = 360.0
_MAXIMUM_INDEX_MARK_RECORDER_AGE_SECONDS = 90.0
_V51 = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_V52 = "multi_asset_growth_first_5000_evidence_bound_successor_v52"
_V53 = "multi_asset_growth_first_5000_hype_freshness_repair_v53"
_V57 = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_EXTERNAL_ASSET_PROFILES = frozenset({_V51, _V52, _V53, _V57})
_SOL_OBSERVER = Path(
    "data/runtime/bidirectional_cohort/latest_v51_sol_route_native_one_blocker_shadow.json"
)
_SOL_ROUTE = "range_onset_bidirectional_v1|SOL"
_SOL_EXPERIMENT = "collect_route_native_one_blocker_shadow"
_DECISION_OVERRIDES = Path(
    "configs/research/cohort_improvement_decision_overrides_v51.json"
)
_INDEX_MARK_RECORDER_STATUS = Path(
    "data/runtime/research/hip3_index_mark_recorder_latest.json"
)
_EXTERNAL_ASSET_CATALOG = Path("configs/research/v51_external_asset_pipeline.json")
_MAXIMUM_EXTERNAL_OBSERVER_AGE_SECONDS = 120.0
_HYPE_NATIVE_LIFECYCLE_STATUS = Path(
    "data/runtime/research/hype_native_v54_prospective_lifecycle_latest.json"
)
_MAXIMUM_HYPE_NATIVE_LIFECYCLE_AGE_SECONDS = 90.0
_MAXIMUM_ROUTE_LIFECYCLE_AGE_SECONDS = 300.0
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument("--opportunity-matrix", type=Path)
    parser.add_argument("--sol-one-blocker-observer", type=Path, default=_SOL_OBSERVER)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument(
        "--maximum-checkpoint-age-seconds",
        type=float,
        default=_MAXIMUM_CHECKPOINT_AGE_SECONDS,
    )
    parser.add_argument(
        "--maximum-sol-observer-age-seconds",
        type=float,
        default=_MAXIMUM_SOL_OBSERVER_AGE_SECONDS,
    )
    _add_research_source_arguments(parser)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def _add_research_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--index-mark-recorder-status",
        type=Path,
        default=_INDEX_MARK_RECORDER_STATUS,
    )
    parser.add_argument(
        "--maximum-index-mark-recorder-age-seconds",
        type=float,
        default=_MAXIMUM_INDEX_MARK_RECORDER_AGE_SECONDS,
    )
    parser.add_argument(
        "--external-asset-catalog",
        type=Path,
        default=_EXTERNAL_ASSET_CATALOG,
    )
    parser.add_argument(
        "--maximum-external-observer-age-seconds",
        type=float,
        default=_MAXIMUM_EXTERNAL_OBSERVER_AGE_SECONDS,
    )
    parser.add_argument(
        "--hype-native-lifecycle-status",
        type=Path,
        default=_HYPE_NATIVE_LIFECYCLE_STATUS,
    )
    parser.add_argument(
        "--maximum-hype-native-lifecycle-age-seconds",
        type=float,
        default=_MAXIMUM_HYPE_NATIVE_LIFECYCLE_AGE_SECONDS,
    )


def refresh(args: argparse.Namespace) -> dict[str, object]:
    """Build and atomically publish one source-bound digest."""
    raw = args.checkpoint.read_bytes()
    checkpoint = _mapping(json.loads(raw), "improvement checkpoint")
    _validate_checkpoint(checkpoint)
    observed_at = datetime.now(UTC)
    _validate_checkpoint_freshness(
        checkpoint, observed_at, args.maximum_checkpoint_age_seconds
    )
    mark_capture = _load_index_mark_capture(
        args.index_mark_recorder_status,
        observed_at=observed_at,
        maximum_age_seconds=args.maximum_index_mark_recorder_age_seconds,
    )
    source_audit = _mapping(checkpoint.get("audit"), "improvement checkpoint audit")
    audit, matrix_evidence = _attach_opportunity_matrix(
        checkpoint, source_audit, args.opportunity_matrix
    )
    successor = v58.load_v58_successor_observer_for_profile(audit, observed_at)
    overrides, override_raw = _load_decision_overrides(args.decision_overrides)
    _validate_override_identity(overrides, audit)
    route_lifecycles = _load_route_lifecycles(args, overrides, audit, observed_at)
    observer = _load_sol_observer(args, audit, overrides, observed_at)
    external_assets = _external_assets_for_profile(args, audit, observed_at)
    hype_native = load_hype_native_for_profile(
        args.hype_native_lifecycle_status,
        audit,
        observed_at=observed_at,
        maximum_age_seconds=args.maximum_hype_native_lifecycle_age_seconds,
    )
    signal_capture = _load_index_signals(audit, observed_at=observed_at)
    report = _build_report(checkpoint, audit, overrides, observer)
    report["active_hypothesis_lifecycle_statuses"] = route_lifecycles.statuses
    _attach_capture_statuses(report, mark_capture, signal_capture, external_assets)
    if hype_native is not None:
        report["hype_native_prospective_lifecycle"] = hype_native.status
    evidence = _report_evidence(
        args,
        raw,
        override_raw,
        matrix_evidence,
        None if observer is None else observer.source,
        mark_capture,
        signal_capture,
        external_assets,
        hype_native,
    )
    evidence["active_hypothesis_lifecycle_statuses"] = route_lifecycles.evidence
    _attach_successor_observer(report, evidence, successor)
    return _publish_report(args, checkpoint, report, evidence)


def _load_route_lifecycles(
    args: argparse.Namespace,
    overrides: Record,
    audit: Record,
    observed_at: datetime,
) -> ActiveRouteLifecycleCollection:
    """Load exact active-route status under one bounded freshness contract."""
    return load_active_route_lifecycle_statuses(
        overrides,
        audit,
        overrides_path=args.decision_overrides,
        project_root=_PROJECT_ROOT,
        observed_at=observed_at,
        maximum_age_seconds=_MAXIMUM_ROUTE_LIFECYCLE_AGE_SECONDS,
    )


def _publish_report(
    args: argparse.Namespace,
    checkpoint: Record,
    report: dict[str, object],
    evidence: dict[str, object],
) -> dict[str, object]:
    """Publish one atomic digest after all source validation succeeds."""
    report.update(
        generated_at_utc=datetime.now(UTC).isoformat(),
        source_checkpoint_generated_at_utc=_text(
            checkpoint.get("generated_at_utc"), "checkpoint generation time"
        ),
        material_state_sha256=_material_digest(report),
        evidence=evidence,
    )
    write_atomic_json(args.out, report)
    append_material_report(args.history, report)
    return report


def _build_report(
    checkpoint: Record,
    audit: Record,
    overrides: Record,
    observer: ProspectiveExperimentEvidence | None,
) -> dict[str, object]:
    """Build the continuous report from one validated evidence snapshot."""
    digest = build_cohort_improvement_digest(audit, experiment_overrides=overrides)
    if observer is not None:
        digest = attach_prospective_experiment_evidence(digest, observer)
    return build_continuous_improvement_report(checkpoint, digest)


def _attach_opportunity_matrix(
    checkpoint: Record,
    audit: Record,
    path: Path | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Attach a current-run report-only matrix without mutating the checkpoint."""
    output = dict(audit)
    if path is None:
        return output, None
    raw = path.read_bytes()
    matrix = _mapping(json.loads(raw), "opportunity matrix")
    _validate_matrix_identity(matrix, checkpoint, audit)
    output["execution_opportunity_matrix"] = dict(matrix)
    return output, {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _validate_matrix_identity(
    matrix: Record,
    checkpoint: Record,
    audit: Record,
) -> None:
    """Reject a matrix from another run or active configuration."""
    evidence = _mapping(matrix.get("evidence"), "opportunity matrix evidence")
    run = _mapping(audit.get("run"), "improvement audit run")
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if evidence.get("run_id") != run.get("run_id"):
        raise ValueError("opportunity matrix run identity mismatch")
    if generation.get("matches_runtime") is not True:
        raise ValueError("opportunity matrix requires current runtime configuration")
    if evidence.get("config") != generation.get("source_path"):
        raise ValueError("opportunity matrix config identity mismatch")


def _report_evidence(
    args: argparse.Namespace,
    checkpoint_raw: bytes,
    override_raw: bytes,
    matrix: dict[str, object] | None,
    observer: dict[str, object] | None,
    mark_capture: MarkCaptureHealth,
    signal_capture: SignalCaptureHealth | None,
    external_assets: ExternalAssetPipeline | None,
    hype_native: HypeNativeLifecycleEvidence | None,
) -> dict[str, object]:
    """Build exact source evidence for one improvement report."""
    evidence: dict[str, object] = {
        "checkpoint": {
            "path": str(args.checkpoint.resolve()),
            "sha256": sha256(checkpoint_raw).hexdigest(),
            "bytes": len(checkpoint_raw),
        },
        "decision_overrides": {
            "path": str(args.decision_overrides.resolve()),
            "sha256": sha256(override_raw).hexdigest(),
            "bytes": len(override_raw),
        },
    }
    if matrix is not None:
        evidence["opportunity_matrix"] = matrix
    if observer is not None:
        evidence["sol_route_native_observer"] = observer
    if mark_capture.evidence is not None:
        evidence["index_mark_recorder"] = mark_capture.evidence
    if signal_capture is not None and signal_capture.evidence is not None:
        evidence["index_signal_capture"] = signal_capture.evidence
    if external_assets is not None:
        evidence["external_asset_pipeline"] = external_assets.evidence
    if hype_native is not None:
        evidence["hype_native_prospective_lifecycle"] = hype_native.evidence
    return evidence


def _attach_capture_statuses(
    report: dict[str, object],
    marks: MarkCaptureHealth,
    signals: SignalCaptureHealth | None,
    external: ExternalAssetPipeline | None,
) -> None:
    """Attach report-only capture states without changing research decisions."""
    report["index_mark_capture"] = marks.status
    if signals is not None:
        report["index_signal_capture"] = signals.status
    if external is not None:
        report["external_asset_pipeline"] = external.status


def _attach_successor_observer(
    report: dict[str, object],
    evidence: dict[str, object],
    successor: v58.SuccessorObserverEvidence | None,
) -> None:
    """Attach the exact successor lane without changing active decisions."""
    if successor is None:
        return
    report["successor_observer"] = successor.status
    evidence["successor_observer"] = successor.evidence


def _external_assets_for_profile(
    args: argparse.Namespace, audit: Record, observed_at: datetime
) -> ExternalAssetPipeline | None:
    """Attach external candidates to exact profiles sharing the research lane."""
    run = _mapping(audit.get("run"), "improvement audit run")
    if run.get("profile_id") not in _EXTERNAL_ASSET_PROFILES:
        return None
    return _load_external_assets(args, observed_at)


def _load_external_assets(
    args: argparse.Namespace, observed_at: datetime
) -> ExternalAssetPipeline:
    """Load the source-bound report-only external candidate lane."""
    return load_external_asset_pipeline(
        args.external_asset_catalog,
        observed_at=observed_at,
        maximum_observer_age_seconds=args.maximum_external_observer_age_seconds,
    )


def _load_sol_observer(
    args: argparse.Namespace,
    audit: Record,
    overrides: Record,
    observed_at: datetime,
) -> ProspectiveExperimentEvidence | None:
    """Load the exact v51 observer only for its matching active profile."""
    run = _mapping(audit.get("run"), "improvement audit run")
    profile = _text(run.get("profile_id"), "improvement profile id")
    if profile != _V51:
        return None
    routes = _mapping(overrides.get("routes"), "research override routes")
    sol = _mapping(routes.get(_SOL_ROUTE), "SOL research override")
    if sol.get("next_experiment") != _SOL_EXPERIMENT:
        return None
    identity = ObserverIdentity(
        _text(run.get("run_id"), "improvement run id"),
        profile,
        _text(run.get("profile_fingerprint"), "improvement profile fingerprint"),
    )
    return load_sol_route_native_observer(
        args.sol_one_blocker_observer,
        identity,
        observed_at=observed_at,
        maximum_age_seconds=args.maximum_sol_observer_age_seconds,
    )


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


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _material_digest(value: Record) -> str:
    return material_state_sha256(value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only portfolio improvement monitor."""
    return run_monitor(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
