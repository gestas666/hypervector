#!/usr/bin/env python3
"""Publish outcome-blind BTC liquidation development book-timing coverage."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    open_text_reader,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.btc_liquidation_covariate_audit import (
    verify_covariate_acquisition_audit,
)
from hypervector.research.btc_liquidation_covariate_inputs import (
    ArchiveHour,
    archive_hour_pairs,
    load_book_rows,
)
from hypervector.research.btc_liquidation_covariate_models import (
    BookTimingCoverage,
    ReplayEpisode,
)
from hypervector.research.btc_liquidation_covariate_partition import (
    bind_development_episodes,
    development_windows,
)
from hypervector.research.btc_liquidation_covariate_preflight import (
    assess_development_book_timing,
)
from hypervector.research.btc_liquidation_covariate_windows import (
    MergedCovariateWindow,
)
from hypervector.research.btc_liquidation_episode_storage import (
    verify_liquidation_episode_bundle,
)

_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"
_MODE = "v58_btc_liquidation_development_book_timing_preflight"
_PARTITION = "development"
_HORIZONS_MS = (30_000, 120_000, 300_000, 900_000)
_JOURNAL = Path(
    "docs/research-journal/"
    "v58-btc-short-liquidation-continuation-data-preflight-20260822-v8.json"
)
_PLAN = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_covariate_acquisition_plan_20260822_v1.json"
)
_TREATMENT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_treatment_episodes_20260822_v1"
)
_AUDIT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_covariate_archive_audit_20260822_v1"
)
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_development_book_timing_preflight_20260822_v1"
)
_JOURNAL_SHA256 = "4c6203a782a18dae0a61d866cc33959ab03a42e014096995f54aec45a1f79ff2"
_PLAN_SHA256 = "edb288c72992c6c3f4225f7225585e2548c318e010470c5c7b550ca2cb00b421"
_TREATMENT_SHA256 = "fa1377cf18c3f57edc042896478f2c6a935c997aaa51b0b7edd1294d01af3314"
_AUDIT_SHA256 = "6f941d30712dd90708391753abdd17792186f4a154a7edcd30d1e0f9fe2a3724"
_TASK_EVIDENCE_SHA256 = (
    "6149d440c0a652fae6d9b960e74e588bd499fafc2d8f9ae56239e0e6196fddcd"
)


@dataclass(frozen=True)
class _FrozenInputs:
    windows: tuple[MergedCovariateWindow, ...]
    episodes: tuple[ReplayEpisode, ...]
    hours: tuple[ArchiveHour, ...]
    evidence: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed development-only timing-preflight parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--plan", type=Path, default=_PLAN)
    parser.add_argument("--treatment-bundle", type=Path, default=_TREATMENT)
    parser.add_argument("--audit-bundle", type=Path, default=_AUDIT)
    parser.add_argument("--partition", choices=(_PARTITION,), default=_PARTITION)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Verify frozen inputs and publish development timestamp coverage once."""
    if args.partition != _PARTITION:
        raise ValueError("BTC liquidation preflight is development-only")
    if args.out.exists():
        raise FileExistsError(f"development preflight already exists: {args.out}")
    frozen = _load_frozen_inputs(args)
    timing = assess_development_book_timing(
        frozen.windows,
        frozen.episodes,
        frozen.hours,
        horizons_ms=_HORIZONS_MS,
        book_loader=load_book_rows,
    )
    if _timing_horizons(timing) != _HORIZONS_MS:
        raise ValueError("development timing horizons differ from the frozen contract")
    _verify_inputs_unchanged(args, frozen.evidence)
    report = build_preflight_report(timing, evidence=frozen.evidence)
    publish_preflight(args.out, report, timing)
    return args.out


def build_preflight_report(
    timing: tuple[BookTimingCoverage, ...],
    *,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Build a timestamp-only report with no strategy-return calculation."""
    _validate_timing(timing)
    delays = tuple(
        row.entry_delay_ms for row in timing if row.entry_delay_ms is not None
    )
    complete = sum(row.technical_complete for row in timing)
    return {
        "schema_version": 1,
        "mode": _MODE,
        "hypothesis_id": _HYPOTHESIS,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "partition": _PARTITION,
        "status": (
            "technical_complete" if complete == len(timing) else "technical_incomplete"
        ),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "strategy_mutation": False,
            "market_returns_computed": False,
            "pnl_computed": False,
            "market_prices_reported": False,
            "book_prices_parsed_for_depth_validation": True,
            "validation_and_pseudo_outcomes_opened": False,
        },
        "horizons_ms": list(_HORIZONS_MS),
        "summary": {
            "episodes": len(timing),
            "technical_complete": complete,
            "technical_incomplete": len(timing) - complete,
            "maximum_entry_delay_ms": max(delays, default=None),
        },
        "evidence": dict(evidence),
    }


def publish_preflight(
    output: Path,
    report: Mapping[str, object],
    timing: tuple[BookTimingCoverage, ...],
) -> None:
    """Atomically publish timestamp rows and their hash-bound report once."""
    _validate_timing(timing)

    def writer(staging: Path) -> None:
        timing_path = staging / "timing.jsonl.gz"
        _write_timing(timing_path, timing)
        report_path = staging / "report.json"
        write_json(report_path, dict(report))
        files = {path.name: file_evidence(path) for path in (report_path, timing_path)}
        write_json(
            staging / "manifest.json",
            {"schema_version": "immutable_evidence_manifest_v1", "files": files},
        )

    publish_immutable_directory(output, writer)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the development-only preflight and print the immutable output path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


def _load_frozen_inputs(args: argparse.Namespace) -> _FrozenInputs:
    evidence = _verify_root_evidence(args)
    plan = _load_json_object(args.plan, "covariate plan")
    windows = development_windows(plan)
    rows = _load_jsonl_objects(
        args.treatment_bundle / "eligible_episodes.jsonl.gz",
        "eligible treatment episodes",
    )
    episodes = bind_development_episodes(rows, windows)
    tasks = _load_jsonl_objects(
        args.audit_bundle / "task_evidence.jsonl.gz",
        "covariate task evidence",
    )
    hours = archive_hour_pairs(tasks)
    return _FrozenInputs(windows, episodes, hours, evidence)


def _verify_root_evidence(args: argparse.Namespace) -> dict[str, object]:
    _verify_exact_file(args.journal, _JOURNAL_SHA256, "revision-eight journal")
    _validate_journal(_load_json_object(args.journal, "revision-eight journal"))
    _verify_exact_file(args.plan, _PLAN_SHA256, "covariate plan")
    treatment_manifest = args.treatment_bundle / "manifest.json"
    _verify_exact_file(treatment_manifest, _TREATMENT_SHA256, "treatment manifest")
    verify_liquidation_episode_bundle(args.treatment_bundle)
    audit_report = args.audit_bundle / "audit.json"
    task_evidence = args.audit_bundle / "task_evidence.jsonl.gz"
    _verify_exact_file(audit_report, _AUDIT_SHA256, "covariate audit")
    _verify_exact_file(task_evidence, _TASK_EVIDENCE_SHA256, "task evidence")
    verify_covariate_acquisition_audit(args.audit_bundle)
    return {
        "journal": _file_record(args.journal),
        "plan": _file_record(args.plan),
        "treatment_manifest": _file_record(treatment_manifest),
        "audit_report": _file_record(audit_report),
        "task_evidence": _file_record(task_evidence),
    }


def _verify_inputs_unchanged(
    args: argparse.Namespace,
    expected: Mapping[str, object],
) -> None:
    observed = _verify_root_evidence(args)
    if observed != expected:
        raise ValueError(
            "BTC liquidation preflight inputs changed during materialization"
        )


def _validate_journal(payload: Mapping[str, object]) -> None:
    metrics = payload.get("metrics")
    contract = payload.get("operational_experiment_contract")
    valid = (
        payload.get("schema_version") == 1
        and payload.get("hypothesis_id") == _HYPOTHESIS
        and payload.get("revision_number") == 8
        and payload.get("execution_authority") == "none"
        and payload.get("automatic_promotion") is False
        and isinstance(metrics, Mapping)
        and metrics.get("stage") == "covariate_archive_complete_outcomes_unopened"
        and metrics.get("strategy_outcomes_inspected") is False
        and isinstance(contract, Mapping)
        and contract.get("decision_delay_ms") == 10_000
        and contract.get("outcome_horizons_ms") == list(_HORIZONS_MS)
    )
    if not valid:
        raise ValueError("revision-eight outcome-unopened journal contract drifted")


def _verify_exact_file(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    if file_evidence(path)["sha256"] != expected_sha256:
        raise ValueError(f"{label} checksum drifted: {path}")


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_json_object(path: Path, label: str) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_jsonl_objects(
    path: Path,
    label: str,
) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    with open_text_reader(path) as handle:
        for line in handle:
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise ValueError(f"{label} contains a non-object row")
            rows.append(payload)
    return tuple(rows)


def _validate_timing(timing: tuple[BookTimingCoverage, ...]) -> None:
    if not timing:
        raise ValueError("development timing result must be nonempty")
    identities = tuple(row.episode_id for row in timing)
    if len(identities) != len(set(identities)):
        raise ValueError("development timing result contains duplicate identities")
    horizons = _timing_horizons(timing)
    for row in timing:
        _validate_timing_row(row, horizons)


def _timing_horizons(
    timing: tuple[BookTimingCoverage, ...],
) -> tuple[int, ...]:
    if not timing:
        raise ValueError("development timing result must be nonempty")
    return tuple(horizon for horizon, _ in timing[0].horizon_book_times_ms)


def _validate_timing_row(
    row: BookTimingCoverage,
    horizons: tuple[int, ...],
) -> None:
    observed = tuple(horizon for horizon, _ in row.horizon_book_times_ms)
    complete = row.entry_book_time_ms is not None and all(
        timestamp is not None for _, timestamp in row.horizon_book_times_ms
    )
    delay_matches = (
        row.entry_book_time_ms is None
        and row.entry_delay_ms is None
        or row.entry_book_time_ms is not None
        and row.entry_delay_ms == row.entry_book_time_ms - row.decision_time_ms
    )
    if observed != horizons or row.technical_complete != complete or not delay_matches:
        raise ValueError("development timing row does not reconcile")


def _write_timing(
    path: Path,
    timing: tuple[BookTimingCoverage, ...],
) -> None:
    with gzip_text_writer(path) as handle:
        for row in timing:
            payload = {
                "schema_version": "btc_liquidation_book_timing_coverage_v1",
                "episode_id": row.episode_id,
                "decision_time_ms": row.decision_time_ms,
                "entry_book_time_ms": row.entry_book_time_ms,
                "entry_delay_ms": row.entry_delay_ms,
                "horizon_book_times_ms": [
                    {"horizon_ms": horizon, "book_time_ms": timestamp}
                    for horizon, timestamp in row.horizon_book_times_ms
                ],
                "technical_complete": row.technical_complete,
            }
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
