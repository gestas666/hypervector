"""Development-only reporting for the frozen HIP-3 Krown mechanism."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.research.hip3_krown_trend_resumption_candidate import (
    Hip3KrownDevelopmentResult,
    hip3_krown_trend_resumption_portfolio_config,
)
from hypervector.research.hip3_krown_trend_resumption_path import (
    krown_partition_trade_path_quality,
)
from hypervector.research.hip3_oil_shock_reversion_friction import (
    Hip3OilFrictionContract,
)
from hypervector.research.hip3_oil_shock_reversion_reporting import (
    _fold_report,
    _partition_economics,
    _scaled_hypothesis,
    _status,
    _window,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult, summarize_trades


def build_hip3_krown_development_report(
    result: Hip3KrownDevelopmentResult,
    development_bars: pd.DataFrame,
    friction: Hip3OilFrictionContract,
) -> dict[str, object]:
    """Serialize exact development economics with zero execution authority."""
    if result.symbol != friction.execution.symbol:
        raise ValueError("Krown result and friction symbols must match")
    path = krown_partition_trade_path_quality(development_bars, result.development)
    return {
        "schema_version": "hip3_krown_trend_resumption_development_v1",
        "symbol": result.symbol,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "strategy_identity": _strategy_identity(result),
        "scaled_account_hypothesis": _scaled_hypothesis(friction),
        "friction_contract": _friction_contract(result, friction),
        "development_window": _window(result.development),
        "development_economics": _partition_economics(
            result.development, result.symbol
        ),
        "development_folds": [
            _fold_report(fold, result.symbol) for fold in result.folds
        ],
        "technical_path_evidence": path,
        "research_disposition": _disposition(result.development, result.folds, path),
        "out_of_sample_economics": result.out_of_sample_economics,
        "validation_accessed": False,
        "holdout_accessed": False,
        "limitations": _limitations(friction),
    }


def _strategy_identity(result: Hip3KrownDevelopmentResult) -> dict[str, object]:
    return {
        "provider_id": result.proposed_provider_id,
        "profile_id": result.proposed_profile_id,
        "timeframe": "15m",
        "config": asdict(result.signal),
    }


def _friction_contract(
    result: Hip3KrownDevelopmentResult,
    friction: Hip3OilFrictionContract,
) -> dict[str, object]:
    nominal = hip3_krown_trend_resumption_portfolio_config(
        result.execution, result.signal, stress=False
    )
    stress = hip3_krown_trend_resumption_portfolio_config(
        result.execution, result.signal, stress=True
    )
    measured = asdict(friction)
    measured.pop("execution")
    return {
        **measured,
        "effective_taker_fee_rate": result.execution.effective_taker_fee_rate,
        "venue_max_leverage": result.execution.venue_max_leverage,
        "applied_strategy_execution": {
            "leverage": nominal.leverage,
            "normalized_notional_usd": result.execution.notional_usd,
            "fixed_take_profit": False,
            "stop_distance_bps": result.signal.protective_stop_bps,
            "maximum_hold_bars": nominal.max_hold_bars,
            "maximum_hold_seconds": nominal.max_hold_seconds,
            "nominal_slippage_bps_per_side": nominal.entry_slippage_bps,
            "stress_slippage_bps_per_side": stress.entry_slippage_bps,
            "primary_exit": "opposite_completed_rsi_ema_turn_or_ema_alignment_loss",
            "risk_high_column": nominal.risk_high_column,
            "risk_low_column": nominal.risk_low_column,
            "entry_risk_high_column": nominal.entry_risk_high_column,
            "entry_risk_low_column": nominal.entry_risk_low_column,
        },
    }


def _disposition(
    development: MuPartitionResult,
    folds: tuple[MuPartitionResult, ...],
    path: dict[str, object],
) -> dict[str, object]:
    stress = summarize_trades(development.stress.trades)
    checks = {
        "technical_paths_resolved": path["status"] == "resolved",
        "nominal_net_positive": development.nominal.net_pnl_usd > 0.0,
        "stress_net_positive": development.stress.net_pnl_usd > 0.0,
        "stress_positive_without_largest_winner": (
            stress["all"].net_without_largest_winner_usd > 0.0
        ),
        "long_stress_positive_without_largest_winner": (
            stress["long"].trades > 0
            and stress["long"].net_without_largest_winner_usd > 0.0
        ),
        "short_stress_positive_without_largest_winner": (
            stress["short"].trades > 0
            and stress["short"].net_without_largest_winner_usd > 0.0
        ),
        "majority_positive_stress_folds": (
            sum(fold.stress.net_pnl_usd > 0.0 for fold in folds) * 2 > len(folds)
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


def _limitations(friction: Hip3OilFrictionContract) -> list[str]:
    limitations = [
        "development evidence is hypothesis formation rather than out-of-sample",
        "validation and holdout economics were not evaluated",
        "indicator conjunction and exits are a disclosed translation, not Pine rules",
        "BBO is exact while scaled depth impact is a distributional increment",
        "fee evidence uses current inputs rather than historical fee state",
        "no live strategy, asset, risk, sizing, or configuration change is authorized",
    ]
    if friction.live_stress_floor_bps_per_side is not None:
        limitations.append(
            f"live stress floor uses {friction.live_slippage_observations} sparse "
            "mixed-strategy BRENTOIL observations rather than a stable distribution"
        )
    return limitations
