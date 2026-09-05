#!/usr/bin/env python3
"""Publish one exact, development-only BRENTOIL Krown replay."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace

import pandas as pd

import hip3_oil_shock_reversion_development as base
import mu_hip3_archive_research as archive
from hypervector.research.hip3_krown_trend_resumption_candidate import (
    evaluate_hip3_krown_trend_resumption_development,
)
from hypervector.research.hip3_krown_trend_resumption_reporting import (
    build_hip3_krown_development_report,
)
from hypervector.research.hip3_krown_trend_resumption_signals import (
    Hip3KrownTrendResumptionConfig,
)
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_oil_shock_reversion_friction import (
    build_hip3_oil_friction_contract,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveExecution,
    canonical_mu_archive_windows,
)
from hypervector.research.mu_hip3_archive_reporting import archive_coverage

ReportBuilder = base.ReportBuilder


def build_parser() -> argparse.ArgumentParser:
    """Return the network-free Krown development command parser."""
    parser = base.build_parser()
    parser.description = __doc__
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable Krown evidence with zero execution authority."""
    return base.run_command(args, report_builder=report_builder or _evaluate_exact)


def _evaluate_exact(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate the frozen Krown mechanism from exact local evidence."""
    return base.evaluate_exact_with_replay(args, _replay)


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
    """Replay the single preregistered 15-minute Krown candidate."""
    symbol = str(args.symbol)
    live_floor, observations = base._live_stress_input(args, symbol)
    contract = build_hip3_oil_friction_contract(
        symbol=symbol,
        venue_max_leverage=archive._qualification_leverage(qualification, symbol),
        fee_profile=archive._mapping(fee_report.get("profile"), "fee profile"),
        liquidity_profile=archive._mapping(
            liquidity_report.get("profile"), "liquidity profile"
        ),
        live_stress_floor_bps_per_side=live_floor,
        live_slippage_observations=observations,
    )
    bars, attachment = attach_official_funding(midpoints["15m"].bars, funding)
    execution = _krown_execution(contract.execution, bars)
    windows = canonical_mu_archive_windows(
        max(item.archive_start_utc for item in midpoints.values()),
        min(item.archive_end_utc for item in midpoints.values()),
    )
    result = evaluate_hip3_krown_trend_resumption_development(
        bars,
        execution,
        windows=windows,
        signal=Hip3KrownTrendResumptionConfig(),
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    report = build_hip3_krown_development_report(result, development, contract)
    return {
        **report,
        "funding_input": funding_input,
        "funding_attachment": asdict(attachment),
        "archive_coverage": archive_coverage(midpoints["15m"], audit, "15m"),
    }


def _krown_execution(
    execution: MuArchiveExecution,
    bars: pd.DataFrame,
) -> MuArchiveExecution:
    """Translate the shared friction evidence to the frozen 15-minute cadence."""
    return replace(
        execution,
        maximum_hold_bars=Hip3KrownTrendResumptionConfig().maximum_hold_bars,
        **archive._risk_path_columns(bars),
    )


def main() -> int:
    """Run the exact local replay and print only its immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
