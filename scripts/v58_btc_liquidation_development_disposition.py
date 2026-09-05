#!/usr/bin/env python3
"""Publish the preregistered V58 BTC development statistical disposition."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import gzip
import json
from pathlib import Path
from typing import Literal

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.data.research_database import ResearchDatabase
from hypervector.research.btc_liquidation_covariate_models import (
    BurstArm,
    CandidateBranch,
)
from hypervector.research.btc_liquidation_development_statistics import (
    BootstrapEstimate,
    DevelopmentArmEconomics,
    EconomicObservation,
    economic_observations,
    holm_adjust,
    monthly_summaries,
    parse_development_arm_results,
    purge_arm_group,
    regime_summaries,
    stationary_day_bootstrap,
    summarize_observations,
)

_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"
_RAW = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_development_economics_20260822_v1"
)
_CORRECTION = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_development_economics_metadata_correction_20260822_v1.json"
)
_REVISION = Path(
    "docs/research-journal/"
    "v58-btc-short-liquidation-continuation-data-preflight-20260822-v12.json"
)
_DATABASE = Path("data/research/market.duckdb")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_development_disposition_20260822_v1"
)
_RAW_MANIFEST_SHA256 = (
    "fd5004174c1f9658be629b21cf932053af3fb87ee2ac401bb62dfcc1d327ec65"
)
_RAW_REPORT_SHA256 = "97b4f780efdcf3e748450c4e9c3e393a75482a66c6dbdfb527fa037d620ed5f2"
_RAW_RESULTS_SHA256 = "318e6d540ff1f7ddb82185b35cebb97982c8dd49863c6a74f225844d43a2ce2b"
_CORRECTION_SHA256 = "02a568e4844ca55c57ab541f1ba91dffb86a7a1fcf82003099ac8ded9b54f1cd"
_REVISION_SHA256 = "9bc3e4f4f1582d0836cb6f06c43a0b745b25dce0ec048805a3c63bb0c91386b4"
_BRANCHES: tuple[CandidateBranch, ...] = (
    "continuation_long",
    "exhaustion_reclaim_long",
)
_ARMS: tuple[BurstArm, ...] = ("5s_p95", "5s_p99", "15s_p95", "15s_p99")
_HORIZONS = (30_000, 120_000, 300_000, 900_000)
_PRIMARY_ARM: BurstArm = "5s_p95"
_PRIMARY_HORIZON_MS = 300_000
_OVERLAP_HORIZON_MS = 900_000
_BOOTSTRAP_RESAMPLES = 10_000
_BOOTSTRAP_BLOCK_DAYS = 7
_BOOTSTRAP_SEED = 20260822


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed development-only disposition parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-bundle", type=Path, default=_RAW)
    parser.add_argument("--metadata-correction", type=Path, default=_CORRECTION)
    parser.add_argument("--revision", type=Path, default=_REVISION)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Compute and publish development statistics after revision-13 guard."""
    if args.output.exists():
        raise FileExistsError(f"development disposition already exists: {args.output}")
    preregistration = _require_preregistration(args.database)
    rows, evidence = _load_inputs(args, preregistration)
    report, diagnostics = build_disposition(rows, evidence=evidence)
    refreshed, refreshed_evidence = _load_inputs(
        args, _require_preregistration(args.database)
    )
    if refreshed != rows or refreshed_evidence != evidence:
        raise RuntimeError("development disposition inputs changed during evaluation")
    _publish(args.output, report, diagnostics)
    return args.output


def validate_preregistration(history: Mapping[str, object]) -> None:
    """Require current revision 13 with values still declared uninspected."""
    revisions = _sequence(history.get("revisions"), "research revisions")
    if not revisions:
        raise ValueError("development disposition has no preregistration")
    latest = _mapping(revisions[-1], "latest revision")
    metrics = _mapping(latest.get("metrics"), "latest metrics")
    evidence = _sequence(latest.get("evidence"), "latest evidence")
    valid = (
        history.get("execution_authority") == "none"
        and latest.get("revision_number") == 13
        and latest.get("revision_id") == history.get("current_revision_id")
        and metrics.get("stage") == "development_statistics_frozen_values_uninspected"
        and metrics.get("development_result_values_inspected") is False
        and metrics.get("validation_outcomes_opened") is False
        and metrics.get("pseudo_holdout_outcomes_opened") is False
        and all(
            _mapping(row, "latest evidence row").get("integrity") == "matching"
            for row in evidence
        )
    )
    if not valid:
        raise ValueError(
            "development disposition requires clean uninspected revision 13"
        )


def evaluate_development_advancement(
    summary: Mapping[str, object],
    bootstrap: BootstrapEstimate | None,
    *,
    holm_adjusted_p_value: float,
    months: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Apply every frozen development-to-validation advancement criterion."""
    count = summary.get("count")
    mean = summary.get("mean_nominal_return_bps")
    stress = summary.get("mean_stressed_return_bps")
    concentration = summary.get("largest_positive_pnl_contribution")
    stable = all(
        not (
            _integer(month.get("count"), "month count") >= 20
            and _decimal(month.get("mean_nominal_return_bps"), "month mean") < 0
        )
        for month in months.values()
    )
    criteria = {
        "at_least_100_retained_resolved": isinstance(count, int) and count >= 100,
        "positive_nominal_mean": isinstance(mean, Decimal) and mean > 0,
        "positive_nominal_95pct_lower_bound": bootstrap is not None
        and bootstrap.lower > 0.0,
        "holm_one_sided_p_below_0_05": holm_adjusted_p_value < 0.05,
        "positive_stressed_mean": isinstance(stress, Decimal) and stress > 0,
        "no_materially_negative_month": stable,
        "largest_winner_at_most_30pct": isinstance(concentration, Decimal)
        and concentration <= Decimal("0.30"),
    }
    return {
        "criteria": criteria,
        "advance_to_validation": all(criteria.values()),
    }


def build_disposition(
    rows: tuple[DevelopmentArmEconomics, ...],
    *,
    evidence: Mapping[str, object],
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    """Build primary branch tests and non-rescuing diagnostics."""
    primary = {branch: _primary_branch(rows, branch) for branch in _BRANCHES}
    raw_p_values = {
        branch: _bootstrap_p_value(primary[branch].get("nominal_bootstrap"))
        for branch in _BRANCHES
    }
    adjusted = holm_adjust(raw_p_values)
    advancing: list[str] = []
    for branch in _BRANCHES:
        result = primary[branch]
        gate = evaluate_development_advancement(
            _mapping(result["summary"], "primary summary"),
            result["nominal_bootstrap"],
            holm_adjusted_p_value=adjusted[branch],
            months=_nested_mapping(result["months"], "primary months"),
        )
        result["holm_adjusted_one_sided_p_value"] = adjusted[branch]
        result["development_advancement"] = gate
        if gate["advance_to_validation"] is True:
            advancing.append(branch)
    diagnostics = tuple(
        _diagnostic(rows, branch, arm, horizon)
        for branch in _BRANCHES
        for arm in _ARMS
        for horizon in _HORIZONS
    )
    report = _report(primary, advancing, evidence)
    return report, diagnostics


def _primary_branch(
    rows: tuple[DevelopmentArmEconomics, ...], branch: CandidateBranch
) -> dict[str, object]:
    selected = tuple(
        row for row in rows if row.branch == branch and row.arm == _PRIMARY_ARM
    )
    group = purge_arm_group(
        rows,
        branch=branch,
        arm=_PRIMARY_ARM,
        overlap_horizon_ms=_OVERLAP_HORIZON_MS,
    )
    observations = economic_observations(group.retained, horizon_ms=_PRIMARY_HORIZON_MS)
    nominal = _bootstrap(observations, "nominal_return_bps")
    stressed = _bootstrap(observations, "stressed_return_bps")
    return {
        "branch": branch,
        "arm": _PRIMARY_ARM,
        "horizon_ms": _PRIMARY_HORIZON_MS,
        "raw_episode_count": len(selected),
        "entry_status_counts": dict(Counter(row.entry_status for row in selected)),
        "eligible_before_purge": len(group.retained) + len(group.suppressed),
        "retained_after_purge": len(group.retained),
        "overlap_suppressed": len(group.suppressed),
        "resolved_after_purge": len(observations),
        "retained_technical_outcomes": len(group.retained) - len(observations),
        "summary": summarize_observations(observations),
        "nominal_bootstrap": nominal,
        "stressed_bootstrap": stressed,
        "months": monthly_summaries(observations),
        "regimes_descriptive_only": regime_summaries(observations),
    }


def _diagnostic(
    rows: tuple[DevelopmentArmEconomics, ...],
    branch: CandidateBranch,
    arm: BurstArm,
    horizon_ms: int,
) -> dict[str, object]:
    selected = tuple(row for row in rows if row.branch == branch and row.arm == arm)
    group = purge_arm_group(
        rows,
        branch=branch,
        arm=arm,
        overlap_horizon_ms=_OVERLAP_HORIZON_MS,
    )
    observations = economic_observations(group.retained, horizon_ms=horizon_ms)
    return {
        "branch": branch,
        "arm": arm,
        "horizon_ms": horizon_ms,
        "raw_episode_count": len(selected),
        "eligible_before_purge": len(group.retained) + len(group.suppressed),
        "retained_after_purge": len(group.retained),
        "overlap_suppressed": len(group.suppressed),
        "resolved_after_purge": len(observations),
        "summary": summarize_observations(observations),
        "selection_authority": "none",
    }


def _bootstrap(
    rows: tuple[EconomicObservation, ...],
    value: Literal["nominal_return_bps", "stressed_return_bps"],
) -> BootstrapEstimate | None:
    if not rows:
        return None
    return stationary_day_bootstrap(
        rows,
        value=value,
        expected_block_days=_BOOTSTRAP_BLOCK_DAYS,
        resamples=_BOOTSTRAP_RESAMPLES,
        seed=_BOOTSTRAP_SEED,
    )


def _report(
    primary: Mapping[str, object],
    advancing: list[str],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "v58_btc_liquidation_development_disposition",
        "hypothesis_id": _HYPOTHESIS,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": (
            "development_survivor_validation_still_sealed"
            if advancing
            else "development_rejected_validation_sealed"
        ),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "strategy_mutation": False,
            "automatic_promotion": False,
            "primary_arm": _PRIMARY_ARM,
            "primary_horizon_ms": _PRIMARY_HORIZON_MS,
            "diagnostics_can_rescue_primary": False,
            "validation_outcomes_opened": False,
            "pseudo_holdout_outcomes_opened": False,
        },
        "advancing_branches": advancing,
        "primary_branches": _json_safe(primary),
        "evidence": dict(evidence),
    }


def _load_inputs(
    args: argparse.Namespace,
    preregistration: Mapping[str, object],
) -> tuple[tuple[DevelopmentArmEconomics, ...], dict[str, object]]:
    manifest_path = args.raw_bundle / "manifest.json"
    report_path = args.raw_bundle / "report.json"
    results_path = args.raw_bundle / "results.jsonl.gz"
    _verify_exact(manifest_path, _RAW_MANIFEST_SHA256, "raw manifest")
    manifest = _json_object(manifest_path, "raw manifest")
    verify_file_evidence(args.raw_bundle, manifest.get("files"))
    _verify_exact(report_path, _RAW_REPORT_SHA256, "raw report")
    report = _json_object(report_path, "raw report")
    _validate_raw_report(report)
    _verify_exact(results_path, _RAW_RESULTS_SHA256, "raw results")
    _verify_exact(args.metadata_correction, _CORRECTION_SHA256, "metadata correction")
    _verify_exact(args.revision, _REVISION_SHA256, "revision 12")
    rows = parse_development_arm_results(_jsonl_rows(results_path))
    if len(rows) != 2_836:
        raise ValueError("raw development arm count differs from frozen artifact")
    evidence = {
        "preregistration": dict(preregistration),
        "revision_12": _file_record(args.revision),
        "raw_manifest": _file_record(manifest_path),
        "raw_report": _file_record(report_path),
        "raw_results": _file_record(results_path),
        "metadata_correction": _file_record(args.metadata_correction),
    }
    return rows, evidence


def _validate_raw_report(report: Mapping[str, object]) -> None:
    contract = _mapping(report.get("contract"), "raw report contract")
    summary = _mapping(report.get("summary"), "raw report summary")
    valid = (
        report.get("status") == "development_materialized_not_disposed"
        and contract.get("execution_authority") == "none"
        and contract.get("validation_outcomes_opened") is False
        and contract.get("pseudo_holdout_outcomes_opened") is False
        and summary.get("episode_count") == 1_531
        and summary.get("arm_record_count") == 2_836
    )
    if not valid:
        raise ValueError("raw development report contract is invalid")


def _require_preregistration(database: Path) -> dict[str, object]:
    history = ResearchDatabase(database).portfolio_research_history(_HYPOTHESIS)
    validate_preregistration(history)
    latest = _mapping(_sequence(history["revisions"], "revisions")[-1], "latest")
    return {
        "revision_number": latest["revision_number"],
        "revision_id": latest["revision_id"],
    }


def _publish(
    output: Path,
    report: Mapping[str, object],
    diagnostics: tuple[dict[str, object], ...],
) -> None:
    def writer(staging: Path) -> None:
        report_path = staging / "report.json"
        write_json(report_path, _json_safe(report))
        diagnostics_path = staging / "diagnostics.jsonl.gz"
        with gzip_text_writer(diagnostics_path) as handle:
            for row in diagnostics:
                handle.write(json.dumps(_json_safe(row), sort_keys=True))
                handle.write("\n")
        write_json(
            staging / "manifest.json",
            {
                "schema_version": "immutable_evidence_manifest_v1",
                "files": {
                    path.name: file_evidence(path)
                    for path in (report_path, diagnostics_path)
                },
            },
        )

    publish_immutable_directory(output, writer)


def _bootstrap_p_value(value: object) -> float:
    return 1.0 if value is None else _bootstrap_estimate(value).one_sided_p_value


def _bootstrap_estimate(value: object) -> BootstrapEstimate:
    if not isinstance(value, BootstrapEstimate):
        raise ValueError("primary bootstrap has an invalid type")
    return value


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, BootstrapEstimate):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json_object(path: Path, label: str) -> dict[str, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _jsonl_rows(path: Path) -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(_mapping(json.loads(line), "raw result"))
    return tuple(rows)


def _verify_exact(path: Path, sha256: str, label: str) -> None:
    if file_evidence(path).get("sha256") != sha256:
        raise ValueError(f"{label} SHA-256 differs from frozen evidence")


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nested_mapping(value: object, label: str) -> Mapping[str, Mapping[str, object]]:
    outer = _mapping(value, label)
    return {str(key): _mapping(item, label) for key, item in outer.items()}


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError(f"{label} must be an exact Decimal")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the guarded disposition and print its immutable output path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
