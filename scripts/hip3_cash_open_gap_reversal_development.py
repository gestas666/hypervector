#!/usr/bin/env python3
"""Publish one exact, development-only SP500 or SPCX gap-reversal replay."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace

import pandas as pd

import hip3_opening_range_breakout_development as session
import mu_hip3_archive_research as archive
from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    evaluate_hip3_cash_open_gap_reversal_development,
)
from hypervector.research.hip3_cash_open_gap_reversal_reporting import (
    build_hip3_cash_open_gap_reversal_report,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_archive_reporting import archive_coverage


ReportBuilder = session.ReportBuilder


def build_parser() -> argparse.ArgumentParser:
    """Return the explicit local-only development parser."""
    parser = session.build_parser()
    parser.description = __doc__
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable zero-authority evidence after source revalidation."""
    builder = report_builder or _evaluate_exact
    return session.base.run_command(args, report_builder=builder)


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
    """Replay only the preregistered 15-minute development mechanism."""
    symbol = str(args.symbol)
    cost = archive._load_json(args.cost_contract)
    leverage = archive._qualification_leverage(qualification, symbol)
    execution, signal = _execution_contract(symbol, leverage, liquidity_report, cost)
    session._require_fee_source(fee_report, cost)
    bars, attachment, windows = session.session_bars_and_windows(midpoints, funding)
    execution = replace(execution, **archive._risk_path_columns(bars))
    result = evaluate_hip3_cash_open_gap_reversal_development(
        bars, execution, windows=windows, signal=signal
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    report = build_hip3_cash_open_gap_reversal_report(result, development, cost)
    return {
        **report,
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "archive_coverage": archive_coverage(midpoints["15m"], audit, "15m"),
    }


def _execution_contract(
    symbol: str,
    venue_max_leverage: float,
    liquidity_report: dict[str, object],
    cost: dict[str, object],
) -> tuple[MuArchiveExecution, Hip3CashOpenGapReversalConfig]:
    """Build exact costs with fixed, non-tuned signal parameters."""
    signal = Hip3CashOpenGapReversalConfig()
    execution = session.base_index_execution_contract(
        symbol,
        venue_max_leverage,
        liquidity_report,
        cost,
        fixed_stop_bps=signal.stop_bps,
        maximum_hold_bars=signal.maximum_hold_bars,
    )
    return execution, signal


def main() -> int:
    """Run one local replay and print only its immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
