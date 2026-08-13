#!/usr/bin/env python3
"""Run a network-free, development-only exact HIP-3 archive diagnostic."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import mu_hip3_archive_research as archive
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.research.hip3_development_diagnostic import (
    build_hip3_development_diagnostic,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveCandidateResult,
    MuArchiveExecution,
    canonical_mu_archive_windows,
    evaluate_hip3_archive_candidates,
)
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows
from hypervector.research.mu_hip3_archive_reporting import (
    archive_coverage,
    family_report,
    family_assessment,
    partition_windows,
)
from hypervector.research.swing_ha_screen import base_trial_grid


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable local diagnostic parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, type=archive._hip3_symbol_argument)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--funding", required=True, type=Path)
    parser.add_argument("--start", required=True, type=archive._utc_argument)
    parser.add_argument("--end", required=True, type=archive._utc_argument)
    parser.add_argument("--qualification-report", required=True, type=Path)
    parser.add_argument("--liquidity-report", required=True, type=Path)
    parser.add_argument("--archive-audit-report", required=True, type=Path)
    parser.add_argument("--nominal-latency-bps-per-side", type=float, default=1.0)
    parser.add_argument("--stress-latency-bps-per-side", type=float, default=2.0)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate development evidence and publish no strategy authority."""
    archive.require_new_outputs(args.output)
    generator = _generator_identity()
    qualification, liquidity, audit = _load_inputs(args)
    start, end = _validated_scope(args, audit)
    database_evidence = _file_reference(args.database)
    midpoints = _load_midpoints(args, audit, start, end)
    funding, funding_input = archive._load_funding_input(
        args, str(args.symbol), start.floor("h"), end.ceil("h"), _forbidden_fetch
    )
    execution = archive._execution(args, qualification, liquidity, str(args.symbol))
    bars, funding_evidence, executions, results = _evaluate_development(
        midpoints, funding, execution
    )
    report = _build_report(
        args,
        midpoints,
        audit,
        funding_input,
        funding_evidence,
        executions,
        results,
        bars,
        generator,
        database_evidence,
    )
    _require_inputs_unchanged(args, generator, database_evidence, funding_input)
    write_immutable_json(args.output, report)
    return report


def _load_inputs(
    args: argparse.Namespace,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        archive._load_json(args.qualification_report),
        archive._load_json(args.liquidity_report),
        archive._load_json(args.archive_audit_report),
    )


def _validated_scope(
    args: argparse.Namespace,
    audit: dict[str, object],
) -> tuple[pd.Timestamp, pd.Timestamp]:
    archive._require_complete_audit(audit)
    archive._require_paired_trade_audit(audit)
    return archive._audit_bound_scope(args, audit, str(args.symbol))


def _load_midpoints(
    args: argparse.Namespace,
    audit: dict[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Hip3MidpointBars]:
    midpoints = {
        timeframe: archive.build_hip3_midpoint_bars(
            args.database,
            symbol=str(args.symbol),
            bar_minutes=minutes,
            start_utc=start,
            end_utc=end,
        )
        for timeframe, minutes, _hold in archive._TIMEFRAME_SPECS
    }
    for midpoint in midpoints.values():
        archive._reconcile_archive(midpoint, audit, str(args.symbol))
    loaded = archive._load_venue_path_midpoints(args, midpoints, audit)
    archive._require_venue_path_midpoints(loaded)
    archive._require_qualification_mark_start(loaded)
    return loaded


def _evaluate_development(
    midpoints: dict[str, Hip3MidpointBars],
    funding: pd.DataFrame,
    base_execution: MuArchiveExecution,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, object],
    dict[str, MuArchiveExecution],
    tuple[MuArchiveCandidateResult, ...],
]:
    starts = [item.archive_start_utc for item in midpoints.values()]
    ends = [item.archive_end_utc for item in midpoints.values()]
    windows = canonical_mu_archive_windows(max(starts), min(ends))
    bars_by_timeframe: dict[str, pd.DataFrame] = {}
    evidence: dict[str, object] = {}
    executions: dict[str, MuArchiveExecution] = {}
    results: list[MuArchiveCandidateResult] = []
    for timeframe, _minutes, hold_bars in archive._TIMEFRAME_SPECS:
        bars, attached = attach_official_funding(midpoints[timeframe].bars, funding)
        execution = replace(
            base_execution,
            maximum_hold_bars=hold_bars,
            **archive._risk_path_columns(bars),
        )
        bars_by_timeframe[timeframe] = bars
        evidence[timeframe] = asdict(attached)
        executions[timeframe] = execution
        results.append(_evaluate_one(bars, execution, timeframe, windows))
    return bars_by_timeframe, evidence, executions, tuple(results)


def _evaluate_one(
    bars: pd.DataFrame,
    execution: MuArchiveExecution,
    timeframe: str,
    windows: MuChronologicalWindows,
) -> MuArchiveCandidateResult:
    return evaluate_hip3_archive_candidates(
        bars,
        execution,
        timeframe=timeframe,
        partition_names=("development",),
        windows=windows,
        swing_configs=base_trial_grid(),
        breakout_configs=archive.default_breakout_pressure_grid(),
    )


def _build_report(
    args: argparse.Namespace,
    midpoints: dict[str, Hip3MidpointBars],
    audit: dict[str, object],
    funding_input: dict[str, object],
    funding_evidence: dict[str, object],
    executions: dict[str, MuArchiveExecution],
    results: tuple[MuArchiveCandidateResult, ...],
    bars: dict[str, pd.DataFrame],
    generator: dict[str, object],
    database_evidence: dict[str, object],
) -> dict[str, object]:
    diagnostic = build_hip3_development_diagnostic(
        results,
        bars,
        expected_symbol=str(args.symbol),
        expected_start_utc=args.start,
        expected_end_utc=args.end,
        funding_complete=funding_input.get("complete") is True,
    )
    selected = diagnostic["development_selected_track"]
    timeframe = str(selected["timeframe"])
    return {
        **_base_report(args),
        "funding_input": funding_input,
        "funding_attachment": funding_evidence,
        "route_specific_friction": {
            key: asdict(value) for key, value in executions.items()
        },
        "selected_route_inputs": {
            "execution_friction": asdict(executions[timeframe]),
            "funding_attachment": funding_evidence[timeframe],
        },
        "archive_coverage": _coverage(midpoints, audit, results),
        "development_search": _search_report(results),
        **diagnostic,
        "source_evidence": _source_evidence(args, database_evidence),
        "generator_identity": generator,
        "limitations": _limitations(),
    }


def _base_report(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": "hip3_development_only_diagnostic_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "symbol": str(args.symbol),
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "place_attempted": False,
        "runtime_strategy_changed": False,
        "live_roster_changed": False,
        "frozen_window": {
            "start_utc": args.start.isoformat(),
            "end_utc": args.end.isoformat(),
        },
    }


def _coverage(
    midpoints: dict[str, Hip3MidpointBars],
    audit: dict[str, object],
    results: tuple[MuArchiveCandidateResult, ...],
) -> dict[str, object]:
    return {
        result.timeframe: archive_coverage(
            midpoints[result.timeframe], audit, result.timeframe
        )
        for result in results
    }


def _search_report(
    results: tuple[MuArchiveCandidateResult, ...],
) -> dict[str, object]:
    return {
        result.timeframe: {
            "windows": partition_windows(result),
            "families": {
                family.family: family_report(family, family_assessment(family))
                for family in result.families
            },
        }
        for result in results
    }


def _source_evidence(
    args: argparse.Namespace,
    database_evidence: dict[str, object],
) -> dict[str, object]:
    return {
        "database": {"path": str(args.database.resolve()), **database_evidence},
        "archive_audit": _file_reference(args.archive_audit_report),
        "qualification": _file_reference(args.qualification_report),
        "liquidity": _file_reference(args.liquidity_report),
        "funding": _file_reference(args.funding),
        "funding_manifest": _file_reference(args.funding.parent / "manifest.json"),
    }


def _require_inputs_unchanged(
    args: argparse.Namespace,
    generator: dict[str, object],
    database_evidence: dict[str, object],
    funding_input: dict[str, object],
) -> None:
    root = Path(__file__).resolve().parents[1]
    require_unchanged_dependencies(generator, root)
    require_unchanged_file(args.database, database_evidence)
    archive._require_funding_input_unchanged(args, str(args.symbol), funding_input)


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    script = Path(__file__).resolve()
    paths = loaded_project_source_paths(root, script)
    return source_dependency_identity(root, paths)


def _file_reference(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"HIP-3 development input does not exist: {path}")
    return {"path": str(path.resolve()), **file_evidence(path)}


def _forbidden_fetch(*_args: object, **_kwargs: object) -> pd.DataFrame:
    raise RuntimeError("HIP-3 development diagnostic forbids network funding fetches")


def _limitations() -> list[str]:
    return [
        "development economics are selection evidence and are not out-of-sample",
        "validation and holdout economics were neither evaluated nor reported",
        "visible quotes exclude queue position and post-snapshot adverse selection",
        "current fee inputs are not historical fee-state reconstruction",
        "no live authority, strategy mutation, or roster change is granted",
    ]


def main() -> int:
    """Run the local diagnostic and print only its output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
