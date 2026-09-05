#!/usr/bin/env python3
"""Materialize frozen V58 BTC liquidation economics in development only."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd

from hypervector.data.hl_funding_evidence import (
    HlFundingEvidence,
    read_complete_hl_funding_evidence,
)
from hypervector.data.oxa_candles import (
    OxaCandleRequest,
    read_complete_candle_evidence,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    open_text_reader,
    verify_file_evidence,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.research.btc_liquidation_covariate_audit import (
    verify_covariate_acquisition_audit,
)
from hypervector.research.btc_liquidation_covariate_inputs import (
    ArchiveHour,
    archive_hour_pairs,
    load_book_rows,
    load_trade_rows,
)
from hypervector.research.btc_liquidation_covariate_models import (
    FundingSettlement,
    ReplayEpisode,
)
from hypervector.research.btc_liquidation_covariate_partition import (
    bind_development_episodes,
    development_windows,
    hours_for_window,
)
from hypervector.research.btc_liquidation_covariate_windows import (
    MergedCovariateWindow,
)
from hypervector.research.btc_liquidation_development_materializer import (
    evaluate_development_episode,
    funding_settlements,
)
from hypervector.research.btc_liquidation_development_storage import (
    build_development_materialization_report,
    episode_arm_records,
    publish_development_materialization,
)
from hypervector.research.btc_liquidation_episode_storage import (
    verify_liquidation_episode_bundle,
)

_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"
_JOURNAL = Path(
    "docs/research-journal/"
    "v58-btc-short-liquidation-continuation-data-preflight-20260822-v10.json"
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
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/BTC/"
    "20251201T000000000000Z_20260601T000000000000Z_funding/funding.parquet"
)
_REGIME = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_causal_regime_evidence_20260822_v1"
)
_CANDLES = Path(
    "data/cache/vendor/0xarchive/hyperliquid/BTC/"
    "20251130T000000000000Z_20260601T000000000000Z_candles_5m"
)
_DATABASE = Path("data/research/market.duckdb")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_development_economics_20260822_v1"
)
_JOURNAL_SHA256 = "1473ceca929d552388e337b7c40dcea0465b92028ab145a94c8d3352b697c83a"
_PLAN_SHA256 = "edb288c72992c6c3f4225f7225585e2548c318e010470c5c7b550ca2cb00b421"
_TREATMENT_SHA256 = "fa1377cf18c3f57edc042896478f2c6a935c997aaa51b0b7edd1294d01af3314"
_AUDIT_SHA256 = "6f941d30712dd90708391753abdd17792186f4a154a7edcd30d1e0f9fe2a3724"
_TASK_SHA256 = "6149d440c0a652fae6d9b960e74e588bd499fafc2d8f9ae56239e0e6196fddcd"
_FUNDING_MANIFEST_SHA256 = (
    "80c126a24e7716f5c547d7d852924243dd98094516466240d0efa937aff1ab42"
)
_REGIME_MANIFEST_SHA256 = (
    "3d47f6e58a7df78bf5016bb4c689dbf2c536c3482b245e7a40e2bf70e880a492"
)
_DEVELOPMENT_END_MS = 1_780_272_000_000
_HORIZONS_MS = (30_000, 120_000, 300_000, 900_000)
_MAXIMUM_EXTENSION_MS = 35_001


@dataclass(frozen=True)
class _FrozenInputs:
    windows: tuple[MergedCovariateWindow, ...]
    episodes: tuple[ReplayEpisode, ...]
    hours: tuple[ArchiveHour, ...]
    funding: HlFundingEvidence
    settlements: tuple[FundingSettlement, ...]
    regime_labels: pd.DataFrame
    evidence: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed development-only materialization parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--plan", type=Path, default=_PLAN)
    parser.add_argument("--treatment-bundle", type=Path, default=_TREATMENT)
    parser.add_argument("--audit-bundle", type=Path, default=_AUDIT)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--regime-bundle", type=Path, default=_REGIME)
    parser.add_argument("--candle-bundle", type=Path, default=_CANDLES)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Open development economics only after immutable preregistration."""
    if args.output.exists():
        raise FileExistsError(f"development economics already exist: {args.output}")
    preregistration = _require_preregistration(args.database)
    frozen = _load_inputs(args, preregistration)
    records = _materialize(frozen)
    refreshed = _load_inputs(args, _require_preregistration(args.database))
    if refreshed.evidence != frozen.evidence:
        raise RuntimeError("frozen development inputs changed during materialization")
    report = build_development_materialization_report(
        records,
        episode_count=len(frozen.episodes),
        window_count=len(frozen.windows),
        evidence=frozen.evidence,
    )
    publish_development_materialization(args.output, records, report)
    return args.output


def validate_preregistration(history: Mapping[str, object]) -> None:
    """Require a current hash-clean revision that still reports unopened outcomes."""
    revisions = _sequence(history.get("revisions"), "research revisions")
    if not revisions:
        raise ValueError("development materializer has no research preregistration")
    latest = _mapping(revisions[-1], "latest research revision")
    metrics = _mapping(latest.get("metrics"), "latest research metrics")
    evidence = _sequence(latest.get("evidence"), "latest research evidence")
    valid = (
        history.get("execution_authority") == "none"
        and latest.get("revision_number") == 12
        and latest.get("revision_id") == history.get("current_revision_id")
        and metrics.get("stage")
        == "development_materializer_boundary_dedupe_frozen_results_uninspected"
        and metrics.get("strategy_outcomes_inspected") is False
        and metrics.get("validation_outcomes_opened") is False
        and metrics.get("pseudo_holdout_outcomes_opened") is False
        and all(
            _mapping(row, "research evidence").get("integrity") == "matching"
            for row in evidence
        )
    )
    if not valid:
        raise ValueError(
            "development materializer requires current matching results-uninspected revision 12"
        )


def _require_preregistration(database: Path) -> dict[str, object]:
    history = ResearchDatabase(database).portfolio_research_history(_HYPOTHESIS)
    validate_preregistration(history)
    latest = _mapping(
        _sequence(history["revisions"], "research revisions")[-1], "latest revision"
    )
    return {
        "revision_id": latest["revision_id"],
        "revision_number": latest["revision_number"],
        "source_record": _file_record(Path(str(latest["evidence"][0]["path"]))),
    }


def _load_inputs(
    args: argparse.Namespace, preregistration: dict[str, object]
) -> _FrozenInputs:
    evidence = _verify_root_inputs(args)
    plan = _load_json_object(args.plan, "covariate plan")
    windows = development_windows(plan)
    treatment_rows = _load_jsonl_objects(
        args.treatment_bundle / "eligible_episodes.jsonl.gz",
        "eligible treatment episodes",
    )
    episodes = bind_development_episodes(treatment_rows, windows)
    tasks = _load_jsonl_objects(
        args.audit_bundle / "task_evidence.jsonl.gz", "covariate task evidence"
    )
    hours = archive_hour_pairs(tasks)
    funding = read_complete_hl_funding_evidence(args.funding, "BTC")
    funding.require_exact_window(1_764_547_200_000, _DEVELOPMENT_END_MS)
    labels, regime_evidence = _load_regime(args.regime_bundle, args.candle_bundle)
    evidence.update(
        {
            "preregistration": preregistration,
            "funding": funding.evidence,
            "regime": regime_evidence,
        }
    )
    return _FrozenInputs(
        windows,
        episodes,
        hours,
        funding,
        funding_settlements(funding),
        labels,
        evidence,
    )


def _verify_root_inputs(args: argparse.Namespace) -> dict[str, object]:
    _verify_exact(args.journal, _JOURNAL_SHA256, "revision-ten journal")
    journal = _load_json_object(args.journal, "revision-ten journal")
    if (
        journal.get("revision_number") != 10
        or _mapping(journal.get("metrics"), "journal metrics").get(
            "strategy_outcomes_inspected"
        )
        is not False
    ):
        raise ValueError("revision-ten journal is not outcome-unopened")
    _verify_exact(args.plan, _PLAN_SHA256, "covariate plan")
    treatment_manifest = args.treatment_bundle / "manifest.json"
    _verify_exact(treatment_manifest, _TREATMENT_SHA256, "treatment manifest")
    verify_liquidation_episode_bundle(args.treatment_bundle)
    audit_report = args.audit_bundle / "audit.json"
    task_evidence = args.audit_bundle / "task_evidence.jsonl.gz"
    _verify_exact(audit_report, _AUDIT_SHA256, "covariate audit")
    _verify_exact(task_evidence, _TASK_SHA256, "covariate task evidence")
    verify_covariate_acquisition_audit(args.audit_bundle)
    funding_manifest = args.funding.parent / "manifest.json"
    _verify_exact(funding_manifest, _FUNDING_MANIFEST_SHA256, "funding manifest")
    return {
        "journal": _file_record(args.journal),
        "plan": _file_record(args.plan),
        "treatment_manifest": _file_record(treatment_manifest),
        "audit": _file_record(audit_report),
        "task_evidence": _file_record(task_evidence),
        "funding_manifest": _file_record(funding_manifest),
    }


def _load_regime(
    bundle: Path, candle_bundle: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    manifest_path = bundle / "manifest.json"
    _verify_exact(manifest_path, _REGIME_MANIFEST_SHA256, "regime manifest")
    manifest = _load_json_object(manifest_path, "regime manifest")
    verify_file_evidence(bundle, manifest.get("files"))
    report_path = bundle / "report.json"
    report = _load_json_object(report_path, "regime report")
    contract = _mapping(report.get("contract"), "regime contract")
    if (
        report.get("status") != "descriptive_evidence_complete"
        or contract.get("execution_authority") != "none"
        or contract.get("regime_labels_are_entry_gates") is not False
    ):
        raise ValueError("regime evidence has strategy authority")
    _verify_classifier_sources(report)
    _verify_candle_source(candle_bundle)
    labels_path = bundle / "labels.parquet"
    labels = pd.read_parquet(labels_path)
    if len(labels) != 52_704:
        raise ValueError("regime label row count differs from frozen evidence")
    return labels, {
        "manifest": _file_record(manifest_path),
        "report": _file_record(report_path),
        "labels": _file_record(labels_path),
    }


def _verify_classifier_sources(report: Mapping[str, object]) -> None:
    classifier = _mapping(report.get("classifier_evidence"), "classifier evidence")
    sources = _sequence(classifier.get("source_files"), "classifier source files")
    for source in sources:
        row = _mapping(source, "classifier source")
        path = Path(_text(row.get("path"), "classifier source path"))
        observed = file_evidence(path)
        if observed.get("sha256") != row.get("sha256") or observed.get(
            "bytes"
        ) != row.get("bytes"):
            raise ValueError(f"regime classifier source changed: {path}")


def _verify_candle_source(bundle: Path) -> None:
    request = OxaCandleRequest(
        "BTC",
        datetime(2025, 11, 30, tzinfo=UTC),
        datetime(2026, 6, 1, tzinfo=UTC),
        "5m",
        10_000,
        20,
    )
    read_complete_candle_evidence(bundle, request, require_complete_cadence=True)


def _materialize(frozen: _FrozenInputs) -> tuple[dict[str, object], ...]:
    by_id = {row.episode_id: row for row in frozen.episodes}
    if len(by_id) != len(frozen.episodes):
        raise ValueError("development episodes contain duplicate identities")
    output: list[dict[str, object]] = []
    total = len(frozen.windows)
    for index, window in enumerate(frozen.windows, start=1):
        output.extend(_window_records(window, frozen, by_id))
        if index == 1 or index % 50 == 0 or index == total:
            print(
                json.dumps(
                    {"development_windows_complete": index, "total": total},
                    sort_keys=True,
                ),
                flush=True,
            )
    observed = {row.get("episode_id") for row in output}
    if observed != set(by_id):
        raise ValueError("development output does not reconcile treatment identities")
    return tuple(output)


def _window_records(
    window: MergedCovariateWindow,
    frozen: _FrozenInputs,
    by_id: Mapping[str, ReplayEpisode],
) -> tuple[dict[str, object], ...]:
    selected = _extended_hours(frozen.hours, window)
    source_end = min(selected[-1].end_ms, _DEVELOPMENT_END_MS)
    books = load_book_rows(
        tuple(row.book_path for row in selected),
        start_ms=window.start_ms,
        end_ms=source_end,
    )
    trades = load_trade_rows(
        tuple(row.trade_path for row in selected),
        start_ms=window.start_ms,
        end_ms=window.end_ms,
    )
    output: list[dict[str, object]] = []
    for identity in window.episode_ids:
        result = evaluate_development_episode(
            by_id[identity],
            trades=trades,
            books=books,
            funding=frozen.funding,
            settlements=frozen.settlements,
            regime_labels=frozen.regime_labels,
            horizons_ms=_HORIZONS_MS,
        )
        output.extend(episode_arm_records(result))
    return tuple(output)


def _extended_hours(
    hours: tuple[ArchiveHour, ...], window: MergedCovariateWindow
) -> tuple[ArchiveHour, ...]:
    initial = hours_for_window(hours, window, required_end_ms=window.end_ms)
    required = min(window.end_ms + _MAXIMUM_EXTENSION_MS, _DEVELOPMENT_END_MS)
    if required <= window.end_ms:
        return initial
    try:
        return hours_for_window(hours, window, required_end_ms=required)
    except ValueError as exc:
        if "contiguous requested coverage" not in str(exc):
            raise
        return initial


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _load_jsonl_objects(path: Path, label: str) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    with open_text_reader(path) as handle:
        for line in handle:
            payload: object = json.loads(line)
            rows.append(_mapping(payload, label))
    if not rows:
        raise ValueError(f"{label} must be nonempty")
    return tuple(rows)


def _verify_exact(path: Path, sha256: str, label: str) -> None:
    observed = file_evidence(path)
    if observed.get("sha256") != sha256:
        raise ValueError(f"{label} SHA-256 differs from frozen evidence")


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the frozen development materialization and print its output path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
