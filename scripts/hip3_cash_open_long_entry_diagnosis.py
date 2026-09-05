#!/usr/bin/env python3
"""Publish preregistered development-only SPCX long entry attribution."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

import hip3_cash_open_gap_reversal_development as cash_open
import hip3_opening_range_breakout_development as session
import mu_hip3_archive_research as archive
from hypervector.research.hip3_archive_inputs import signal_source_bars
from hypervector.research.hip3_cash_open_gap_path_detail import (
    build_cash_open_gap_path_detail,
)
from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    Hip3CashOpenGapDevelopmentResult,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
)
from hypervector.research.hip3_cash_open_long_entry_diagnosis import (
    build_cash_open_long_entry_diagnosis,
)
from hypervector.research.hip3_cash_open_long_exit_challenger import (
    CashOpenLongExitChallengerResult,
    evaluate_cash_open_long_exit_challengers,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_transfer_sources import FundingAttachmentEvidence
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_archive_reporting import archive_coverage

_HYPOTHESIS_ID = "V56_SPCX_LONG_ENTRY_QUALITY_DIAGNOSIS_20260818_V1"
_ROUTE = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX|long"
_FEATURES = (
    "opening_gap_bps",
    "opening_reversal_bps",
    "gap_recovery_fraction",
    "decision_spread_bps",
    "decision_imbalance_10",
    "public_trade_count",
    "signal_volume",
    "source_snapshot_count",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the exact local-only diagnosis parser."""
    parser = cash_open.build_parser()
    parser.description = __doc__
    parser.add_argument("--preregistration", required=True, type=Path)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: cash_open.ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable diagnosis bound to its preregistration bytes."""
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
    """Replay the frozen long control and serialize causal entry features."""
    symbol = str(args.symbol)
    preregistration = archive._load_json(args.preregistration)
    _validate_preregistration(preregistration)
    cost = archive._load_json(args.cost_contract)
    leverage = archive._qualification_leverage(qualification, symbol)
    execution, signal = cash_open._execution_contract(
        symbol, leverage, liquidity_report, cost
    )
    session._require_fee_source(fee_report, cost)
    bars, attachment, windows = session.session_bars_and_windows(midpoints, funding)
    execution = replace(execution, **archive._risk_path_columns(bars))
    result = evaluate_cash_open_long_exit_challengers(
        bars, execution, windows=windows, target_bps=(40.0,), signal=signal
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    source = signal_source_bars(development)
    signals = build_hip3_cash_open_gap_reversal_signals(source, signal)
    path_detail = build_cash_open_gap_path_detail(
        _path_result(result, execution, signal), development
    )
    report = build_cash_open_long_entry_diagnosis(
        development,
        signals,
        result.control.development.nominal.trades,
        result.control.development.stress.trades,
        path_detail,
    )
    return _complete_report(
        report, result, preregistration, funding_input, attachment, midpoints, audit
    )


def _path_result(
    result: CashOpenLongExitChallengerResult,
    execution: MuArchiveExecution,
    signal: Hip3CashOpenGapReversalConfig,
) -> Hip3CashOpenGapDevelopmentResult:
    control = result.control
    return Hip3CashOpenGapDevelopmentResult(
        result.symbol,
        execution,
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_research_v1",
        "spcx_cash_open_gap_reversal_15m_development_v1",
        result.windows,
        signal,
        control.development,
        control.folds,
    )


def _complete_report(
    report: dict[str, object],
    result: CashOpenLongExitChallengerResult,
    preregistration: dict[str, object],
    funding_input: dict[str, object],
    attachment: FundingAttachmentEvidence,
    midpoints: dict[str, Hip3MidpointBars],
    audit: dict[str, object],
) -> dict[str, object]:
    unresolved = sum(not row["technical_path"]["resolved"] for row in report["entries"])
    return {
        **report,
        **_report_contract(),
        "symbol": result.symbol,
        "direction": "long",
        "preregistration": preregistration,
        "development_window": {
            "start_utc": result.windows.development_start_utc.isoformat(),
            "end_utc": result.windows.development_end_utc.isoformat(),
        },
        "research_disposition": {
            "status": "DESCRIPTIVE_DIAGNOSTIC_ONLY",
            "unresolved_lifecycles": unresolved,
            "entry_filter_selected": False,
            "live_change_authorized": False,
        },
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "archive_coverage": archive_coverage(midpoints["15m"], audit, "15m"),
        "limitations": [
            "nine development longs are descriptive and cannot establish an edge",
            "validation and holdout remain sealed",
            "unresolved risk paths remain explicit and cannot support promotion",
            "no threshold, entry filter, live strategy, risk, or route change is selected",
        ],
    }


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "validation_accessed": False,
        "holdout_accessed": False,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
    }


def _validate_preregistration(payload: dict[str, object]) -> None:
    """Require exact diagnosis identity, scope, features, and zero authority."""
    if payload.get("hypothesis_id") != _HYPOTHESIS_ID or payload.get("route") != _ROUTE:
        raise ValueError(
            "cash-open entry diagnosis preregistration identity is invalid"
        )
    _require_scope(archive._mapping(payload.get("frozen_scope"), "frozen scope"))
    _require_features(payload.get("causal_feature_contract"))
    _require_authority(archive._mapping(payload.get("authority"), "authority"))


def _require_scope(scope: dict[str, object]) -> None:
    expected = {
        "symbol": "xyz:SPCX",
        "timeframe": "15m",
        "direction": "long_only",
        "validation_accessed": False,
        "holdout_accessed": False,
        "outcome_based_entry_exclusion": False,
        "threshold_search": False,
    }
    if any(scope.get(key) != value for key, value in expected.items()):
        raise ValueError("cash-open entry diagnosis scope is invalid")


def _require_features(value: object) -> None:
    rows = archive._sequence(value, "causal feature contract")
    names = tuple(
        _text(archive._mapping(row, "feature").get("name"), "feature name")
        for row in rows
    )
    available = all(
        archive._mapping(row, "feature").get("available_at_decision") is True
        for row in rows
    )
    if names != _FEATURES or not available:
        raise ValueError("cash-open entry diagnosis feature contract is invalid")


def _require_authority(authority: dict[str, object]) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_change": False,
        "approval_requested": False,
    }
    if any(authority.get(key) != value for key, value in expected.items()):
        raise ValueError("cash-open entry diagnosis authority is invalid")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def main() -> int:
    """Run the local diagnosis and print only its immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
