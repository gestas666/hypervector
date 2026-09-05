#!/usr/bin/env python3
"""Publish one immutable BRENTOIL funding-exhaustion development screen."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.research.brentoil_funding_exhaustion_inputs import (
    BrentFundingExhaustionInputs,
    load_brentoil_funding_exhaustion_inputs,
    require_brentoil_inputs_unchanged,
)
from hypervector.research.funding_price_exhaustion_development import (
    evaluate_funding_price_exhaustion_development,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)

ReportBuilder = Callable[[argparse.Namespace], dict[str, object]]


def build_parser() -> argparse.ArgumentParser:
    """Return the network-free BRENTOIL development command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--funding", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable zero-authority evidence after final revalidation."""
    if args.output.exists():
        raise FileExistsError(f"immutable JSON output exists: {args.output}")
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
    preregistration_evidence = file_evidence(args.preregistration)
    inputs = load_brentoil_funding_exhaustion_inputs(
        args.preregistration, args.database, args.funding
    )
    result = evaluate_funding_price_exhaustion_development(
        inputs.bars,
        inputs.funding,
        inputs.config,
        inputs.costs,
        inputs.spec,
        start_utc=inputs.start_utc,
        end_utc=inputs.end_utc,
    )
    require_brentoil_inputs_unchanged(inputs)
    require_unchanged_file(args.preregistration, preregistration_evidence)
    return _report(inputs, result, preregistration_evidence)


def _report(
    inputs: BrentFundingExhaustionInputs,
    result: dict[str, object],
    preregistration_evidence: dict[str, object],
) -> dict[str, object]:
    decision = str(result["decision"])
    return {
        "schema_version": 1,
        "mode": "brentoil_funding_price_exhaustion_development_v1",
        "symbol": "xyz:BRENTOIL",
        "hypothesis_id": inputs.preregistration["hypothesis_id"],
        "contract": _zero_authority_contract(),
        "preregistration": {
            "path": _portable_path(inputs.preregistration_path),
            **preregistration_evidence,
        },
        "source_evidence": [source.report() for source in inputs.source_references],
        "method": _method(inputs),
        "development_result": result,
        "assessment": _assessment(decision),
        "recommendation": inputs.preregistration.get("recommendation"),
    }


def _zero_authority_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def _method(inputs: BrentFundingExhaustionInputs) -> dict[str, object]:
    return {
        "start_utc": inputs.start_utc.isoformat(),
        "end_exclusive_utc": inputs.end_utc.isoformat(),
        "signal_config": asdict(inputs.config),
        "cost_contract": asdict(inputs.costs),
        "development_spec": asdict(inputs.spec),
        "signal_source": "exact_public_trade_5m_ohlcv",
        "funding_source": "official_hourly_hl_funding_history",
        "gap_policy": "split_reset_and_censor",
        "selection_policy": "fixed_horizons_and_chronological_non_overlap",
    }


def _assessment(decision: str) -> dict[str, object]:
    reasons = {
        "supportive_development_only": (
            "At least one frozen horizon met the preregistered development criteria."
        ),
        "rejected_development_only": (
            "No frozen horizon met the preregistered development criteria."
        ),
        "insufficient_development_evidence": (
            "Every frozen horizon had fewer than ten independent observations."
        ),
    }
    if decision not in reasons:
        raise ValueError(f"unsupported BRENTOIL development decision: {decision}")
    return {
        "disposition": decision,
        "reason": reasons[decision],
        "confidence": "high_technical_low_economic",
        "live_change_supported": False,
        "future_only_validation_required": decision == "supportive_development_only",
        "falsifier": (
            "Update only with corrected source identity or a new preregistered "
            "future-only window; do not retune this development result."
        ),
    }


def _require_report_only(report: dict[str, object]) -> None:
    contract = report.get("contract")
    expected = _zero_authority_contract()
    if not isinstance(contract, dict) or any(
        contract.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("BRENTOIL report-only contract is invalid")


def _generator_identity() -> dict[str, object]:
    root = _project_root()
    paths = loaded_project_source_paths(root, Path(__file__).resolve())
    return source_dependency_identity(root, paths)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_project_root()))
    except ValueError:
        return path.name


def main() -> None:
    """Run the offline immutable development screen."""
    run_command(build_parser().parse_args())


if __name__ == "__main__":
    main()
