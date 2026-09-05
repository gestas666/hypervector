#!/usr/bin/env python3
"""Publish one exact, development-only SP500 or SPCX opening-range replay."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from math import isclose
from pathlib import Path

import pandas as pd

import hip3_oil_shock_reversion_development as base
import mu_hip3_archive_research as archive
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars
from hypervector.research.hip3_opening_range_breakout_candidate import (
    evaluate_hip3_opening_range_breakout_development,
)
from hypervector.research.hip3_opening_range_breakout_reporting import (
    build_hip3_opening_range_development_report,
)
from hypervector.research.hip3_opening_range_breakout_signals import (
    Hip3OpeningRangeBreakoutConfig,
)
from hypervector.research.hip3_transfer_sources import (
    FundingAttachmentEvidence,
    attach_official_funding,
)
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveExecution,
    canonical_mu_archive_windows,
)
from hypervector.research.mu_hip3_archive_reporting import archive_coverage

ReportBuilder = base.ReportBuilder


def build_parser() -> argparse.ArgumentParser:
    """Return the network-free opening-range development parser."""
    parser = base.build_parser()
    parser.description = __doc__
    parser.add_argument("--cost-contract", required=True, type=Path)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
) -> dict[str, object]:
    """Publish immutable opening-range evidence with zero live authority."""
    return base.run_command(args, report_builder=report_builder or _evaluate_exact)


def _evaluate_exact(args: argparse.Namespace) -> dict[str, object]:
    """Evaluate exact local inputs and recheck the frozen cost contract."""
    return evaluate_exact_with_cost_contract(args, _replay)


def evaluate_exact_with_cost_contract(
    args: argparse.Namespace,
    replay_builder: base.ReplayBuilder,
) -> dict[str, object]:
    """Evaluate one session replay and bind its pre-PnL cost contract."""
    cost_reference = base._file_reference(args.cost_contract)
    report = base.evaluate_exact_with_replay(args, replay_builder)
    base._require_sources_unchanged({"cost_contract": cost_reference})
    evidence = dict(report["source_evidence"])
    evidence["cost_contract"] = cost_reference
    return {**report, "source_evidence": evidence}


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
    """Replay the single preregistered 15-minute session mechanism."""
    symbol = str(args.symbol)
    cost = archive._load_json(args.cost_contract)
    leverage = archive._qualification_leverage(qualification, symbol)
    execution, signal = _execution_contract(symbol, leverage, liquidity_report, cost)
    _require_fee_source(fee_report, cost)
    bars, attachment, windows = session_bars_and_windows(midpoints, funding)
    execution = replace(execution, **archive._risk_path_columns(bars))
    result = evaluate_hip3_opening_range_breakout_development(
        bars, execution, windows=windows, signal=signal
    )
    development = bars.loc[bars.index < windows.development_end_utc].copy()
    report = build_hip3_opening_range_development_report(result, development, cost)
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
) -> tuple[MuArchiveExecution, Hip3OpeningRangeBreakoutConfig]:
    """Build the exact preregistered fee, latency, and clearance contract."""
    symbol_cost = _symbol_cost(cost, symbol)
    signal = Hip3OpeningRangeBreakoutConfig(
        clearance_bps=_number(symbol_cost, "frozen_breakout_clearance_bps")
    )
    execution = base_index_execution_contract(
        symbol,
        venue_max_leverage,
        liquidity_report,
        cost,
        fixed_stop_bps=signal.maximum_stop_bps,
        maximum_hold_bars=signal.maximum_hold_bars,
    )
    return execution, signal


def base_index_execution_contract(
    symbol: str,
    venue_max_leverage: float,
    liquidity_report: dict[str, object],
    cost: dict[str, object],
    *,
    fixed_stop_bps: float,
    maximum_hold_bars: int,
) -> MuArchiveExecution:
    """Build exact common index execution without selecting a signal family."""
    profile = archive._mapping(liquidity_report.get("profile"), "liquidity profile")
    if profile.get("symbol") != symbol:
        raise ValueError("opening-range liquidity symbol is not exact")
    symbol_cost = _symbol_cost(cost, symbol)
    contract = archive._mapping(cost.get("portfolio_contract"), "portfolio contract")
    target_notional = _number(contract, "notional_usd_per_position")
    notional = _notional(profile, target_notional)
    stress = archive._mapping(cost.get("stress_contract"), "stress contract")
    fees = archive._mapping(cost.get("fee_evidence"), "fee evidence")
    _reconcile_costs(notional, symbol_cost, fees)
    p90, p99 = _visible_quantiles(notional)
    return MuArchiveExecution(
        effective_taker_fee_rate=_number(fees, "effective_taker_rate"),
        notional_usd=_number(contract, "notional_usd_per_position"),
        venue_max_leverage=venue_max_leverage,
        nominal_latency_bps_per_side=_number(stress, "nominal_latency_bps_per_side"),
        stress_latency_bps_per_side=_number(stress, "stress_latency_bps_per_side"),
        stress_visible_tail_bps_per_side=(p99 - p90) / 2.0,
        fixed_stop_bps=fixed_stop_bps,
        maximum_hold_bars=maximum_hold_bars,
        symbol=symbol,
    )


def _symbol_cost(cost: dict[str, object], symbol: str) -> dict[str, object]:
    """Return the exact frozen cost row for one index symbol."""
    symbols = archive._mapping(cost.get("symbols"), "cost symbols")
    return archive._mapping(symbols.get(symbol), "symbol cost")


def session_bars_and_windows(
    midpoints: dict[str, Hip3MidpointBars],
    funding: pd.DataFrame,
) -> tuple[pd.DataFrame, FundingAttachmentEvidence, MuChronologicalWindows]:
    """Attach funding and derive the common canonical archive windows."""
    bars, attachment = attach_official_funding(midpoints["15m"].bars, funding)
    windows = canonical_mu_archive_windows(
        max(item.archive_start_utc for item in midpoints.values()),
        min(item.archive_end_utc for item in midpoints.values()),
    )
    return bars, attachment, windows


def _notional(profile: dict[str, object], expected: float) -> dict[str, object]:
    rows = archive._sequence(profile.get("notionals"), "liquidity notionals")
    matches = [
        archive._mapping(row, "liquidity notional")
        for row in rows
        if isinstance(row, dict) and row.get("notional_usd") == expected
    ]
    if len(matches) != 1 or matches[0].get("both_complete_rate") != 1.0:
        raise ValueError(
            f"opening-range ${expected:g} visible depth is incomplete or ambiguous"
        )
    return matches[0]


def _visible_quantiles(notional: dict[str, object]) -> tuple[float, float]:
    visible = archive._mapping(
        notional.get("round_trip_visible_cost_bps"), "visible costs"
    )
    p90, p99 = _number(visible, "p90"), _number(visible, "p99")
    if p99 < p90:
        raise ValueError("opening-range visible cost quantiles are inverted")
    return p90, p99


def _reconcile_costs(
    notional: dict[str, object],
    symbol_cost: dict[str, object],
    fees: dict[str, object],
) -> None:
    """Reject any drift from the pre-PnL cost journal."""
    _p90, p99 = _visible_quantiles(notional)
    total = archive._mapping(
        notional.get("round_trip_taker_total_cost_bps"), "taker total costs"
    )
    expected = (
        ("p99_round_trip_visible_cost_bps", p99),
        ("p99_round_trip_taker_total_cost_bps", _number(total, "p99")),
    )
    if any(not isclose(_number(symbol_cost, key), value) for key, value in expected):
        raise ValueError("opening-range liquidity costs drifted from frozen contract")
    fee_rate = _number(fees, "effective_taker_rate")
    if not isclose(_number(total, "p99") - p99, fee_rate * 20_000.0):
        raise ValueError("opening-range total cost does not reconcile to fees")


def _require_fee_source(fee_report: dict[str, object], cost: dict[str, object]) -> None:
    """Require the cost journal to bind the exact fee evidence file."""
    evidence = archive._mapping(cost.get("fee_evidence"), "fee evidence")
    markets = archive._sequence(fee_report.get("markets"), "fee markets")
    rates = {
        archive._mapping(row, "fee market").get("venue", {}).get("taker_fee_rate")
        for row in markets
        if isinstance(archive._mapping(row, "fee market").get("venue"), dict)
    }
    if _number(evidence, "effective_taker_rate") not in rates:
        raise ValueError("opening-range fee report does not contain frozen rate")


def _number(value: dict[str, object], key: str) -> float:
    return archive._number(value.get(key), key)


def main() -> int:
    """Run one exact local replay and print only its immutable output path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
