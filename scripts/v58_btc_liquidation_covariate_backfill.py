#!/usr/bin/env python3
"""Acquire frozen BTC liquidation covariate windows without live authority."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Protocol

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillResult,
    OxaBackfillTask,
    ProgressSink,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    write_immutable_json,
)
from hypervector.data.oxa_trade_renormalization import (
    run_oxa_tasks_with_trade_renormalization,
)
from hypervector.research.btc_liquidation_covariate_windows import (
    CovariateWindowPlan,
    EligibleEpisode,
    FrozenPartition,
    HourlyAcquisitionWindow,
    MergedCovariateWindow,
    build_covariate_window_plan,
    hourly_acquisition_windows,
)
from hypervector.research.btc_liquidation_covariate_audit import (
    publish_covariate_acquisition_audit,
)
from hypervector.research.btc_liquidation_covariate_progress import ProgressReporter
from hypervector.research.btc_liquidation_episode_storage import (
    verify_liquidation_episode_bundle,
)
from hypervector.runtime_env import load_dotenv_if_present


_DEFAULT_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-short-liquidation-continuation-data-preflight-20260822-v4.json"
)
_DEFAULT_TREATMENT_JOURNAL = Path(
    "docs/research-journal/"
    "v58-btc-short-liquidation-continuation-data-preflight-20260822-v7.json"
)
_DEFAULT_TREATMENT_BUNDLE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_treatment_episodes_20260822_v1"
)
_DEFAULT_PLAN = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_covariate_acquisition_plan_20260822_v1.json"
)
_DEFAULT_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_covariate_archive_audit_20260822_v1"
)
_FROZEN_PREREGISTRATION_SHA256 = (
    "4f425bf5339115613a408b6c642cb8196ef862f67c9c09c462ba269b16634994"
)
_FROZEN_TREATMENT_JOURNAL_SHA256 = (
    "353ae8ae252f88d63932daa7c8dac77ad1c688a88e3797c8de125a529671660a"
)
_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"
_DECISION_DELAY_MS = 10_000
_PRE_DECISION_MS = 60_000
_OUTCOME_HORIZON_MS = 15 * 60_000


@dataclass(frozen=True)
class PreparedAcquisition:
    """Fully frozen covariate plan and explicit resumable vendor tasks."""

    plan: CovariateWindowPlan
    hours: tuple[HourlyAcquisitionWindow, ...]
    tasks: tuple[OxaBackfillTask, ...]
    config: OxaBackfillConfig
    payload: dict[str, object]


class TaskRunner(Protocol):
    """Credential-bearing boundary for the explicit resumable task pool."""

    def __call__(
        self,
        config: OxaBackfillConfig,
        *,
        tasks: tuple[OxaBackfillTask, ...],
        api_key: str,
        progress: ProgressSink,
    ) -> tuple[OxaBackfillResult, ...]: ...


def build_parser() -> argparse.ArgumentParser:
    """Build the frozen report-only acquisition command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preregistration", type=Path, default=_DEFAULT_PREREGISTRATION
    )
    parser.add_argument(
        "--treatment-journal", type=Path, default=_DEFAULT_TREATMENT_JOURNAL
    )
    parser.add_argument(
        "--treatment-bundle", type=Path, default=_DEFAULT_TREATMENT_BUNDLE
    )
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--book-max-pages", type=int, default=20)
    parser.add_argument("--trade-max-pages", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--plan-out", type=Path, default=_DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--plan-only", action="store_true")
    return parser


def prepare(args: argparse.Namespace) -> PreparedAcquisition:
    """Verify frozen inputs and publish the exact plan without network I/O."""
    preregistration = _load_bound_json(
        args.preregistration,
        _FROZEN_PREREGISTRATION_SHA256,
        "preregistration",
    )
    journal = _load_bound_json(
        args.treatment_journal,
        _FROZEN_TREATMENT_JOURNAL_SHA256,
        "treatment journal",
    )
    _verify_preregistration(preregistration)
    manifest = verify_liquidation_episode_bundle(args.treatment_bundle)
    _verify_treatment_sources(args, journal, manifest)
    episodes = _load_eligible_episodes(args.treatment_bundle, manifest)
    partitions = _frozen_partitions(preregistration)
    plan = build_covariate_window_plan(episodes, partitions)
    hours = hourly_acquisition_windows(plan)
    tasks = _paired_tasks(hours)
    config = _backfill_config(args, hours)
    payload = _plan_payload(args, preregistration, partitions, plan, hours, tasks)
    _ensure_plan(args.plan_out, payload)
    return PreparedAcquisition(plan, hours, tasks, config, payload)


def run(
    args: argparse.Namespace,
    *,
    api_key: str,
    task_runner: TaskRunner = run_oxa_tasks_with_trade_renormalization,
) -> Path:
    """Publish the frozen plan before executing explicit vendor tasks."""
    if not api_key.strip():
        raise ValueError("OXA_API_KEY is not configured")
    if args.out.exists():
        raise FileExistsError(f"immutable covariate audit exists: {args.out}")
    prepared = prepare(args)
    reporter = ProgressReporter(len(prepared.tasks), args.progress_every)
    results = task_runner(
        prepared.config,
        tasks=prepared.tasks,
        api_key=api_key,
        progress=reporter,
    )
    return publish_covariate_acquisition_audit(
        args.out,
        plan_path=args.plan_out,
        symbol=args.symbol,
        tasks=prepared.tasks,
        results=results,
    )


def _load_bound_json(
    path: Path, expected_sha256: str, label: str
) -> Mapping[str, object]:
    evidence = file_evidence(path)
    if evidence["sha256"] != expected_sha256:
        raise ValueError(f"frozen {label} checksum mismatch: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"frozen {label} must be a JSON object: {path}")
    return payload


def _verify_preregistration(payload: Mapping[str, object]) -> None:
    if (
        payload.get("hypothesis_id") != _HYPOTHESIS
        or payload.get("revision_number") != 4
    ):
        raise ValueError("frozen preregistration identity mismatch")
    if (
        payload.get("execution_authority") != "none"
        or payload.get("automatic_promotion") is not False
    ):
        raise ValueError("frozen preregistration acquired execution authority")
    if not isinstance(payload.get("experiment_contract"), Mapping):
        raise ValueError("frozen preregistration experiment contract is missing")


def _verify_treatment_sources(
    args: argparse.Namespace,
    journal: Mapping[str, object],
    manifest: Mapping[str, object],
) -> None:
    metrics = journal.get("metrics")
    if (
        journal.get("revision_number") != 7
        or journal.get("execution_authority") != "none"
        or not isinstance(metrics, Mapping)
    ):
        raise ValueError("treatment journal identity or authority mismatch")
    expected_state = (
        metrics.get("stage") == "treatment_episodes_complete_covariates_pending"
        and metrics.get("strategy_outcomes_inspected") is False
        and metrics.get("market_covariates_acquired") is False
    )
    if not expected_state:
        raise ValueError("treatment journal is not outcome-blind and covariate-pending")
    if manifest.get("symbol") != args.symbol:
        raise ValueError("treatment bundle symbol differs from acquisition symbol")
    for name in ("manifest.json", "episodes.jsonl.gz", "eligible_episodes.jsonl.gz"):
        _verify_journal_file(
            args.treatment_journal, journal, args.treatment_bundle / name
        )


def _verify_journal_file(
    journal_path: Path,
    journal: Mapping[str, object],
    target: Path,
) -> None:
    evidence = journal.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("treatment journal evidence is missing")
    expected = next(
        (
            row
            for row in evidence
            if isinstance(row, Mapping)
            and _evidence_path(journal_path, row.get("path")) == target.resolve()
        ),
        None,
    )
    observed = file_evidence(target)
    if (
        expected is None
        or expected.get("sha256") != observed["sha256"]
        or expected.get("bytes") != observed["bytes"]
    ):
        raise ValueError(f"treatment journal file evidence mismatch: {target}")


def _evidence_path(journal: Path, raw_path: object) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (journal.parent / path).resolve()


def _load_eligible_episodes(
    bundle: Path,
    manifest: Mapping[str, object],
) -> tuple[EligibleEpisode, ...]:
    episodes: list[EligibleEpisode] = []
    with open_text_reader(bundle / "eligible_episodes.jsonl.gz") as handle:
        for line in handle:
            row = json.loads(line)
            if not isinstance(row, Mapping):
                raise ValueError("eligible treatment row must be a JSON object")
            episode_id = row.get("episode_id")
            end_ms = row.get("end_ms")
            arms = row.get("eligible_arms")
            if not isinstance(episode_id, str) or not episode_id:
                raise ValueError("eligible treatment episode_id is invalid")
            if isinstance(end_ms, bool) or not isinstance(end_ms, int):
                raise ValueError("eligible treatment end_ms is invalid")
            if not isinstance(arms, list) or not arms:
                raise ValueError("eligible treatment arms are empty")
            episodes.append(EligibleEpisode(episode_id, end_ms))
    expected = manifest.get("counts")
    if not isinstance(expected, Mapping) or expected.get("eligible_episodes") != len(
        episodes
    ):
        raise ValueError("eligible treatment count differs from verified manifest")
    return tuple(episodes)


def _frozen_partitions(payload: Mapping[str, object]) -> tuple[FrozenPartition, ...]:
    contract = payload["experiment_contract"]
    if not isinstance(contract, Mapping):
        raise ValueError("frozen experiment contract is malformed")
    partitions = (
        FrozenPartition(
            "development",
            _timestamp_ms(contract, "data_start_utc"),
            _timestamp_ms(contract, "development_end_exclusive_utc"),
        ),
        FrozenPartition(
            "validation",
            _timestamp_ms(contract, "validation_start_utc"),
            _timestamp_ms(contract, "validation_end_exclusive_utc"),
        ),
        FrozenPartition(
            "pseudo_holdout",
            _timestamp_ms(contract, "pseudo_holdout_start_utc"),
            _timestamp_ms(contract, "pseudo_holdout_end_exclusive_utc"),
        ),
    )
    if (
        partitions[0].end_ms != partitions[1].start_ms
        or partitions[1].end_ms != partitions[2].start_ms
    ):
        raise ValueError("frozen experiment partitions are not contiguous")
    return partitions


def _timestamp_ms(contract: Mapping[str, object], key: str) -> int:
    value = contract.get(key)
    if not isinstance(value, str):
        raise ValueError(f"frozen experiment timestamp is missing: {key}")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError(f"frozen experiment timestamp is timezone-naive: {key}")
    return int(timestamp.astimezone(UTC).timestamp() * 1_000)


def _paired_tasks(
    hours: tuple[HourlyAcquisitionWindow, ...],
) -> tuple[OxaBackfillTask, ...]:
    tasks: list[OxaBackfillTask] = []
    for hour in hours:
        start = datetime.fromtimestamp(hour.start_ms / 1_000, tz=UTC)
        end = datetime.fromtimestamp(hour.end_ms / 1_000, tz=UTC)
        tasks.extend(
            (OxaBackfillTask("book", start, end), OxaBackfillTask("trade", start, end))
        )
    return tuple(tasks)


def _backfill_config(
    args: argparse.Namespace,
    hours: tuple[HourlyAcquisitionWindow, ...],
) -> OxaBackfillConfig:
    if not hours:
        raise ValueError("frozen treatment plan contains no acquisition hours")
    return OxaBackfillConfig(
        symbol=args.symbol,
        start=datetime.fromtimestamp(hours[0].start_ms / 1_000, tz=UTC),
        end=datetime.fromtimestamp(hours[-1].end_ms / 1_000, tz=UTC),
        data_root=args.data_root,
        chunk=timedelta(hours=1),
        depth=args.depth,
        workers=args.workers,
        retries=args.retries,
        timeout_seconds=args.timeout_seconds,
        book_max_pages=args.book_max_pages,
        trade_max_pages=args.trade_max_pages,
    )


def _plan_payload(
    args: argparse.Namespace,
    preregistration: Mapping[str, object],
    partitions: tuple[FrozenPartition, ...],
    plan: CovariateWindowPlan,
    hours: tuple[HourlyAcquisitionWindow, ...],
    tasks: tuple[OxaBackfillTask, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v58_btc_liquidation_covariate_acquisition_plan",
        "contract": _plan_contract(),
        "source": _source_evidence(args),
        "frozen_experiment": {
            "hypothesis_id": preregistration["hypothesis_id"],
            "decision_delay_ms": _DECISION_DELAY_MS,
            "pre_decision_ms": _PRE_DECISION_MS,
            "outcome_horizon_ms": _OUTCOME_HORIZON_MS,
        },
        "summary": _plan_summary(plan, hours, tasks),
        "partitions": [_partition_payload(row) for row in partitions],
        "windows": [_window_payload(row) for row in plan.windows],
        "vendor_hours": [_hour_payload(row) for row in hours],
        "tasks": [_task_payload(row) for row in tasks],
    }


def _plan_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "strategy_mutation": False,
        "strategy_outcomes_inspected": False,
        "data_families": ["hyperliquid_native_l2", "hyperliquid_public_trades"],
        "half_open_windows": True,
    }


def _source_evidence(args: argparse.Namespace) -> dict[str, object]:
    return {
        "preregistration": _path_evidence(args.preregistration),
        "treatment_journal": _path_evidence(args.treatment_journal),
        "treatment_manifest": _path_evidence(args.treatment_bundle / "manifest.json"),
        "eligible_episodes": _path_evidence(
            args.treatment_bundle / "eligible_episodes.jsonl.gz"
        ),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _plan_summary(
    plan: CovariateWindowPlan,
    hours: tuple[HourlyAcquisitionWindow, ...],
    tasks: tuple[OxaBackfillTask, ...],
) -> dict[str, object]:
    return {
        "eligible_episodes": len(plan.included_episode_ids),
        "boundary_excluded_episodes": len(plan.boundary_excluded_episode_ids),
        "unassigned_episodes": len(plan.unassigned_episode_ids),
        "merged_windows": len(plan.windows),
        "requested_duration_ms": plan.requested_duration_ms,
        "merged_duration_ms": plan.merged_duration_ms,
        "vendor_hours": len(hours),
        "tasks": len(tasks),
        "book_tasks": sum(row.kind == "book" for row in tasks),
        "trade_tasks": sum(row.kind == "trade" for row in tasks),
    }


def _partition_payload(row: FrozenPartition) -> dict[str, object]:
    return {"name": row.name, "start_ms": row.start_ms, "end_ms": row.end_ms}


def _window_payload(row: MergedCovariateWindow) -> dict[str, object]:
    return {
        "partition": row.partition,
        "start_ms": row.start_ms,
        "end_ms": row.end_ms,
        "episode_ids": list(row.episode_ids),
    }


def _hour_payload(row: HourlyAcquisitionWindow) -> dict[str, int]:
    return {"start_ms": row.start_ms, "end_ms": row.end_ms}


def _task_payload(row: OxaBackfillTask) -> dict[str, str]:
    return {
        "kind": row.kind,
        "start_utc": row.start.isoformat(),
        "end_utc": row.end.isoformat(),
    }


def _ensure_plan(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        observed = json.loads(path.read_text(encoding="utf-8"))
        if observed != payload:
            raise ValueError(f"existing BTC covariate acquisition plan differs: {path}")
        return
    write_immutable_json(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Run plan-only or bounded acquisition with secret-free status output."""
    args = build_parser().parse_args(argv)
    try:
        if args.plan_only:
            prepared = prepare(args)
            output: dict[str, object] = {
                "ok": True,
                "plan_only": True,
                "plan": str(args.plan_out),
                "eligible_episodes": len(prepared.plan.included_episode_ids),
                "vendor_hours": len(prepared.hours),
                "tasks": len(prepared.tasks),
                "execution_authority": "none",
            }
        else:
            load_dotenv_if_present()
            published = run(args, api_key=os.environ.get("OXA_API_KEY", ""))
            output = {
                "ok": True,
                "audit": str(published),
                "coverage_complete": True,
                "execution_authority": "none",
            }
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
