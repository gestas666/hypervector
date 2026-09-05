#!/usr/bin/env python3
"""Publish preregistered development-only SPCX long exit evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

import hip3_cash_open_gap_reversal_development as cash_open
import hip3_opening_range_breakout_development as session
import mu_hip3_archive_research as archive
from hypervector.research.hip3_cash_open_long_exit_challenger import (
    evaluate_cash_open_long_exit_challengers,
)
from hypervector.research.hip3_cash_open_long_exit_reporting import (
    build_cash_open_long_exit_report,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.mu_hip3_archive_reporting import archive_coverage


_HYPOTHESIS_ID = "V56_SPCX_LONG_EXIT_GIVEBACK_CHALLENGER_20260818_V1"
_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX|long"
_TARGETS = (40.0, 60.0, 80.0)


def build_parser() -> argparse.ArgumentParser:
    """Return the exact local-only challenger parser."""
    parser = cash_open.build_parser()
    parser.description = __doc__
    parser.add_argument("--preregistration", required=True, type=Path)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: cash_open.ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable evidence bound to the preregistration bytes."""
    reference = cash_open.session.base._file_reference(args.preregistration)
    preregistration = archive._load_json(args.preregistration)
    _validate_preregistration(preregistration)
    builder = report_builder or _evaluate_exact

    def bound_builder(namespace: argparse.Namespace) -> dict[str, object]:
        report = builder(namespace)
        cash_open.session.base._require_sources_unchanged(
            {"preregistration": reference}
        )
        evidence = dict(report["source_evidence"])
        evidence["preregistration"] = reference
        return {**report, "source_evidence": evidence}

    return cash_open.session.base.run_command(args, report_builder=bound_builder)


def _evaluate_exact(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate exact local inputs under the frozen cost contract."""
    return session.evaluate_exact_with_cost_contract(args, _replay)


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
    """Replay only the long control and three frozen target candidates."""
    symbol = str(args.symbol)
    preregistration = archive._load_json(args.preregistration)
    target_bps = _validate_preregistration(preregistration)
    cost = archive._load_json(args.cost_contract)
    leverage = archive._qualification_leverage(qualification, symbol)
    execution, signal = cash_open._execution_contract(
        symbol, leverage, liquidity_report, cost
    )
    session._require_fee_source(fee_report, cost)
    bars, attachment, windows = session.session_bars_and_windows(midpoints, funding)
    execution = replace(execution, **archive._risk_path_columns(bars))
    result = evaluate_cash_open_long_exit_challengers(
        bars,
        execution,
        windows=windows,
        target_bps=target_bps,
        signal=signal,
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    report = build_cash_open_long_exit_report(
        result, development, preregistration=preregistration
    )
    return {
        **report,
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "archive_coverage": archive_coverage(midpoints["15m"], audit, "15m"),
    }


def _validate_preregistration(payload: dict[str, object]) -> tuple[float, ...]:
    """Require the exact frozen route, scope, targets, and zero authority."""
    if payload.get("hypothesis_id") != _HYPOTHESIS_ID or payload.get("route") != _ROUTE:
        raise ValueError("cash-open challenger preregistration identity is invalid")
    challengers = archive._sequence(payload.get("challengers"), "challengers")
    targets = tuple(
        archive._number(
            archive._mapping(row, "challenger").get("target_bps"), "target_bps"
        )
        for row in challengers
    )
    if targets != _TARGETS:
        raise ValueError("cash-open challenger target family is invalid")
    _require_scope(payload)
    _require_authority(payload)
    return targets


def _require_scope(payload: dict[str, object]) -> None:
    scope = archive._mapping(payload.get("frozen_scope"), "frozen scope")
    valid = (
        scope.get("symbol") == "xyz:SPCX"
        and scope.get("direction") == "long_only"
        and scope.get("validation_accessed") is False
        and scope.get("holdout_accessed") is False
    )
    if not valid:
        raise ValueError("cash-open challenger frozen scope is invalid")


def _require_authority(payload: dict[str, object]) -> None:
    authority = archive._mapping(payload.get("authority"), "authority")
    valid = (
        authority.get("report_only") is True
        and authority.get("execution_authority") == "none"
        and authority.get("automatic_promotion") is False
        and authority.get("live_exit_change") is False
    )
    if not valid:
        raise ValueError("cash-open challenger authority is invalid")


def main() -> int:
    """Run the local replay and print only its immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
