"""Development-only reporting for the frozen HIP-3 opening range."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_reporting import (
    _fold_report,
    _partition_economics,
    _status,
    _window,
)
from hypervector.research.hip3_opening_range_breakout_candidate import (
    Hip3OpeningRangeDevelopmentResult,
    hip3_opening_range_breakout_portfolio_config,
)
from hypervector.research.mu_hip3_archive_reporting import (
    partition_trade_path_quality,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult, summarize_trades


def build_hip3_opening_range_development_report(
    result: Hip3OpeningRangeDevelopmentResult,
    development_bars: pd.DataFrame,
    cost_contract: dict[str, object],
) -> dict[str, object]:
    """Serialize exact development economics with zero execution authority."""
    path = opening_range_partition_trade_path_quality(
        development_bars, result.development
    )
    return {
        "schema_version": "hip3_us_cash_opening_range_development_v1",
        "symbol": result.symbol,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "strategy_identity": _strategy_identity(result),
        "cost_contract": cost_contract,
        "applied_execution": _applied_execution(result),
        "development_window": _window(result.development),
        "development_economics": _partition_economics(
            result.development, result.symbol
        ),
        "development_folds": [
            _fold_report(fold, result.symbol) for fold in result.folds
        ],
        "technical_path_evidence": path,
        "research_disposition": opening_range_development_disposition(
            result.development, result.folds, path
        ),
        "out_of_sample_economics": result.out_of_sample_economics,
        "validation_accessed": False,
        "holdout_accessed": False,
        "limitations": _limitations(),
    }


def opening_range_partition_trade_path_quality(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
) -> dict[str, object]:
    """Require exact mark and quote paths without an L2 decision role."""
    quality = partition_trade_path_quality(
        bars,
        partition,
        timeframe="15m",
        family="swing_ha",
    )
    return {
        "status": quality["status"],
        "decision_source": "0xarchive_public_trade_ohlc_v1",
        "decision_l2_required": False,
        "entry_exit_l2_required": True,
        "risk_path_required": True,
        "adapter_basis": "price_only_session_family_without_pressure_role",
        "nominal": quality["nominal"],
        "stress": quality["stress"],
    }


def opening_range_development_disposition(
    development: MuPartitionResult,
    folds: tuple[MuPartitionResult, ...],
    path: dict[str, object],
) -> dict[str, object]:
    """Apply only the preregistered development and technical checks."""
    stress = summarize_trades(development.stress.trades)
    checks = {
        "technical_paths_resolved": path["status"] == "resolved",
        "nominal_net_positive": development.nominal.net_pnl_usd > 0.0,
        "stress_net_positive": development.stress.net_pnl_usd > 0.0,
        "nominal_profit_factor_above_one": _pf_above_one(
            development.nominal.profit_factor
        ),
        "stress_profit_factor_above_one": _pf_above_one(
            development.stress.profit_factor
        ),
        "stress_positive_without_largest_winner": (
            stress["all"].net_without_largest_winner_usd > 0.0
        ),
        "both_directions_observed": (
            stress["long"].trades > 0 and stress["short"].trades > 0
        ),
        "at_least_two_positive_stress_folds": (
            sum(fold.stress.net_pnl_usd > 0.0 for fold in folds) >= 2
        ),
        "no_liquidations": (
            development.nominal.liquidations + development.stress.liquidations == 0
        ),
    }
    return {
        "status": _status(checks),
        "checks": checks,
        "live_change_proposed": False,
    }


def _strategy_identity(
    result: Hip3OpeningRangeDevelopmentResult,
) -> dict[str, object]:
    config = asdict(result.signal)
    config["closed_session_dates"] = [
        value.isoformat() for value in result.signal.closed_session_dates
    ]
    return {
        "provider_id": result.proposed_provider_id,
        "profile_id": result.proposed_profile_id,
        "timeframe": "15m",
        "config": config,
    }


def _applied_execution(
    result: Hip3OpeningRangeDevelopmentResult,
) -> dict[str, object]:
    nominal = hip3_opening_range_breakout_portfolio_config(
        result.execution, result.signal, stress=False
    )
    stress = hip3_opening_range_breakout_portfolio_config(
        result.execution, result.signal, stress=True
    )
    return {
        "leverage": nominal.leverage,
        "notional_usd": result.execution.notional_usd,
        "margin_fraction": nominal.margin_fraction,
        "target_r_multiple": result.signal.target_r_multiple,
        "minimum_stop_bps": result.signal.minimum_stop_bps,
        "maximum_stop_bps": result.signal.maximum_stop_bps,
        "maximum_hold_seconds": nominal.max_hold_seconds,
        "nominal_slippage_bps_per_side": nominal.entry_slippage_bps,
        "stress_slippage_bps_per_side": stress.entry_slippage_bps,
        "risk_columns": [
            nominal.risk_high_column,
            nominal.risk_low_column,
            nominal.entry_risk_high_column,
            nominal.entry_risk_low_column,
        ],
    }


def _pf_above_one(value: float | None) -> bool:
    return value is not None and value > 1.0


def _limitations() -> list[str]:
    return [
        "development evidence is hypothesis formation rather than out-of-sample",
        "validation and holdout economics were not evaluated",
        "BBO is exact while scaled depth impact is a distributional increment",
        "fee evidence uses current inputs rather than historical fee state",
        "NYSE holiday dates are predeclared for the frozen 2026 archive window",
        "SP500 and SPCX are evaluated independently before portfolio interaction",
        "no live strategy, asset, risk, sizing, or configuration change is authorized",
    ]
