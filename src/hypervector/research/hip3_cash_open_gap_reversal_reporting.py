"""Development-only reporting for HIP-3 cash-open gap reversal."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.research.hip3_cash_open_gap_reversal_candidate import (
    Hip3CashOpenGapDevelopmentResult,
    hip3_cash_open_gap_reversal_portfolio_config,
)
from hypervector.research.hip3_cash_open_gap_path_detail import (
    build_cash_open_gap_path_detail,
)
from hypervector.research.hip3_oil_shock_reversion_reporting import (
    _fold_report,
    _partition_economics,
    _window,
)
from hypervector.research.hip3_opening_range_breakout_reporting import (
    opening_range_development_disposition,
    opening_range_partition_trade_path_quality,
)


def build_hip3_cash_open_gap_reversal_report(
    result: Hip3CashOpenGapDevelopmentResult,
    development_bars: pd.DataFrame,
    cost_contract: dict[str, object],
) -> dict[str, object]:
    """Serialize exact development economics with zero live authority."""
    path = opening_range_partition_trade_path_quality(
        development_bars, result.development
    )
    return {
        "schema_version": "hip3_cash_open_gap_reversal_development_v1",
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
        "technical_path_detail": build_cash_open_gap_path_detail(
            result, development_bars
        ),
        "research_disposition": opening_range_development_disposition(
            result.development, result.folds, path
        ),
        "out_of_sample_economics": result.out_of_sample_economics,
        "validation_accessed": False,
        "holdout_accessed": False,
        "limitations": _limitations(),
    }


def _strategy_identity(
    result: Hip3CashOpenGapDevelopmentResult,
) -> dict[str, object]:
    """Return the exact frozen provider, profile, and signal identity."""
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
    result: Hip3CashOpenGapDevelopmentResult,
) -> dict[str, object]:
    """Return sizing, barrier, cost, and exact risk-path inputs."""
    nominal = hip3_cash_open_gap_reversal_portfolio_config(
        result.execution, result.signal, stress=False
    )
    stress = hip3_cash_open_gap_reversal_portfolio_config(
        result.execution, result.signal, stress=True
    )
    return {
        "leverage": nominal.leverage,
        "notional_usd": result.execution.notional_usd,
        "margin_fraction": nominal.margin_fraction,
        "target_policy": "prior_eligible_cash_session_close",
        "stop_bps": result.signal.stop_bps,
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


def _limitations() -> list[str]:
    """Return the frozen interpretation and deployment limitations."""
    return [
        "development evidence is hypothesis formation rather than out-of-sample",
        "validation and holdout economics were not evaluated",
        "the primary academic evidence predates the 2026 HIP-3 perpetual market",
        "BBO is exact while scaled depth impact is a distributional increment",
        "fee evidence uses current inputs rather than historical fee state",
        "SP500 and SPCX are evaluated independently before portfolio interaction",
        "no live strategy, asset, risk, sizing, or configuration change is authorized",
    ]
