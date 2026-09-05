#!/usr/bin/env python3
"""Publish one exact, development-only CL or BRENTOIL oil replay."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import mu_hip3_archive_research as archive
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_oil_shock_continuation_candidate import (
    evaluate_hip3_oil_shock_continuation_development,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_oil_shock_reversion_candidate import (
    Hip3OilDevelopmentResult,
    evaluate_hip3_oil_shock_reversion_development,
)
from hypervector.research.hip3_oil_shock_reversion_friction import (
    build_hip3_oil_friction_contract,
    observed_live_slippage_floor,
)
from hypervector.research.hip3_oil_shock_reversion_reporting import (
    build_hip3_oil_development_report,
)
from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.mu_hip3_archive_candidate import (
    canonical_mu_archive_windows,
)
from hypervector.research.mu_hip3_archive_reporting import archive_coverage

ReportBuilder = Callable[[argparse.Namespace], dict[str, object]]
ReplayBuilder = Callable[
    [
        argparse.Namespace,
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, Hip3MidpointBars],
        pd.DataFrame,
        dict[str, object],
    ],
    dict[str, object],
]
DevelopmentEvaluator = Callable[..., Hip3OilDevelopmentResult]


def build_parser() -> argparse.ArgumentParser:
    """Return the network-free development-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mechanism",
        choices=("reversion", "continuation"),
        default="reversion",
    )
    parser.add_argument("--symbol", required=True, type=archive._hip3_symbol_argument)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--funding", required=True, type=Path)
    parser.add_argument("--start", required=True, type=archive._utc_argument)
    parser.add_argument("--end", required=True, type=archive._utc_argument)
    parser.add_argument("--qualification-report", required=True, type=Path)
    parser.add_argument("--fee-report", required=True, type=Path)
    parser.add_argument("--liquidity-report", required=True, type=Path)
    parser.add_argument("--archive-audit-report", required=True, type=Path)
    parser.add_argument("--live-execution-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable zero-authority evidence after source revalidation."""
    archive.require_new_outputs(args.output)
    generator = _generator_identity()
    report = (report_builder or _evaluate_exact)(args)
    _require_report_only(report)
    payload = {
        **report,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "generator_identity": generator,
    }
    require_unchanged_dependencies(generator, _project_root())
    write_immutable_json(args.output, payload)
    return payload


def _evaluate_exact(args: argparse.Namespace) -> dict[str, object]:
    return evaluate_exact_with_replay(args, _replay)


def evaluate_exact_with_replay(
    args: argparse.Namespace,
    replay_builder: ReplayBuilder,
) -> dict[str, object]:
    """Load and revalidate exact evidence for one development-only replay."""
    symbol = str(args.symbol)
    qualification = archive._load_json(args.qualification_report)
    fee_report = archive._load_json(args.fee_report)
    liquidity_report = archive._load_json(args.liquidity_report)
    audit = archive._load_json(args.archive_audit_report)
    start, end = _scope(args, audit, symbol)
    sources = _source_references(args)
    midpoints = _load_midpoints(args, audit, start, end, symbol)
    funding, funding_input = archive._load_funding_input(
        args, symbol, start.floor("h"), end.ceil("h"), _forbidden_fetch
    )
    report = replay_builder(
        args,
        qualification,
        fee_report,
        liquidity_report,
        audit,
        midpoints,
        funding,
        funding_input,
    )
    _require_sources_unchanged(sources)
    archive._require_funding_input_unchanged(args, symbol, funding_input)
    return {**report, "source_evidence": sources}


def _scope(
    args: argparse.Namespace, audit: dict[str, object], symbol: str
) -> tuple[pd.Timestamp, pd.Timestamp]:
    archive._require_complete_audit(audit)
    archive._require_paired_trade_audit(audit)
    return archive._audit_bound_scope(args, audit, symbol)


def _load_midpoints(
    args: argparse.Namespace,
    audit: dict[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol: str,
) -> dict[str, Hip3MidpointBars]:
    midpoints = {
        timeframe: archive.build_hip3_midpoint_bars(
            args.database,
            symbol=symbol,
            bar_minutes=minutes,
            start_utc=start,
            end_utc=end,
        )
        for timeframe, minutes, _hold in archive._TIMEFRAME_SPECS
    }
    for midpoint in midpoints.values():
        archive._reconcile_archive(midpoint, audit, symbol)
    loaded = archive._load_venue_path_midpoints(args, midpoints, audit)
    archive._require_venue_path_midpoints(loaded)
    archive._require_qualification_mark_start(loaded)
    return loaded


def _replay(
    args: argparse.Namespace,
    qualification: dict[str, object],
    fee_report: dict[str, object],
    liquidity_report: dict[str, object],
    audit: dict[str, object],
    midpoints: dict[str, Hip3MidpointBars],
    funding: pd.DataFrame,
    funding_input: dict[str, object],
) -> dict[str, object]:
    symbol = str(args.symbol)
    live_floor, live_observations = _live_stress_input(args, symbol)
    contract = build_hip3_oil_friction_contract(
        symbol=symbol,
        venue_max_leverage=archive._qualification_leverage(qualification, symbol),
        fee_profile=archive._mapping(fee_report.get("profile"), "fee profile"),
        liquidity_profile=archive._mapping(
            liquidity_report.get("profile"), "liquidity profile"
        ),
        live_stress_floor_bps_per_side=live_floor,
        live_slippage_observations=live_observations,
    )
    bars, attachment = attach_official_funding(midpoints["5m"].bars, funding)
    execution = replace(
        contract.execution,
        **archive._risk_path_columns(bars),
    )
    windows = canonical_mu_archive_windows(
        max(item.archive_start_utc for item in midpoints.values()),
        min(item.archive_end_utc for item in midpoints.values()),
    )
    result = _development_evaluator(args.mechanism)(
        bars,
        execution,
        windows=windows,
        signal=Hip3OilShockReversionConfig(),
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    report = build_hip3_oil_development_report(result, development, contract)
    return {
        **report,
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "archive_coverage": archive_coverage(midpoints["5m"], audit, "5m"),
    }


def _development_evaluator(mechanism: str) -> DevelopmentEvaluator:
    if mechanism == "continuation":
        return evaluate_hip3_oil_shock_continuation_development
    if mechanism == "reversion":
        return evaluate_hip3_oil_shock_reversion_development
    raise ValueError(f"unsupported oil shock mechanism: {mechanism}")


def _source_references(args: argparse.Namespace) -> dict[str, dict[str, object]]:
    paths = {
        "database": args.database,
        "archive_audit": args.archive_audit_report,
        "qualification": args.qualification_report,
        "fees": args.fee_report,
        "scaled_liquidity": args.liquidity_report,
        "funding": args.funding,
        "funding_manifest": args.funding.parent / "manifest.json",
    }
    live_execution = getattr(args, "live_execution_report", None)
    if live_execution is not None:
        paths["live_execution"] = live_execution
    return {name: _file_reference(path) for name, path in paths.items()}


def _live_stress_input(
    args: argparse.Namespace, symbol: str
) -> tuple[float | None, int]:
    path = getattr(args, "live_execution_report", None)
    if path is None:
        return None, 0
    report = archive._load_json(path)
    return observed_live_slippage_floor(report, symbol)


def _require_sources_unchanged(
    sources: dict[str, dict[str, object]],
) -> None:
    for source in sources.values():
        require_unchanged_file(Path(str(source["path"])), source)


def _require_report_only(report: dict[str, object]) -> None:
    expected = (
        report.get("report_only") is True
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("live_roster_change") is False
        and report.get("out_of_sample_economics") == "WITHHELD_NOT_EVALUATED"
        and report.get("validation_accessed") is False
        and report.get("holdout_accessed") is False
    )
    if not expected:
        raise ValueError("oil development report-only contract is invalid")


def _file_reference(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"oil development input does not exist: {path}")
    return {"path": str(path.resolve()), **file_evidence(path)}


def _generator_identity() -> dict[str, object]:
    root = _project_root()
    paths = loaded_project_source_paths(root, Path(__file__).resolve())
    return source_dependency_identity(root, paths)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _forbidden_fetch(*_args: object, **_kwargs: object) -> pd.DataFrame:
    raise RuntimeError("oil development replay forbids network funding fetches")


def main() -> int:
    """Run one exact local replay and print only the immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
