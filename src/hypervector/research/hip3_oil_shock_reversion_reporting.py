"""Development-only reporting for the frozen HIP-3 oil mechanism."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_candidate import (
    Hip3OilDevelopmentResult,
    hip3_oil_reversion_portfolio_config,
)
from hypervector.research.hip3_oil_shock_reversion_friction import (
    Hip3OilFrictionContract,
)
from hypervector.research.hip3_oil_shock_reversion_path import (
    oil_partition_trade_path_quality,
)
from hypervector.research.mu_hip3_archive_reporting import report_summary
from hypervector.research.mu_hip3_candidate import (
    MuPartitionResult,
    summarize_trades,
)


def build_hip3_oil_development_report(
    result: Hip3OilDevelopmentResult,
    development_bars: pd.DataFrame,
    friction: Hip3OilFrictionContract,
) -> dict[str, object]:
    """Serialize exact development economics with zero execution authority."""
    if result.symbol != friction.execution.symbol:
        raise ValueError("oil result and friction symbols must match")
    mechanism = _mechanism(result)
    path = oil_partition_trade_path_quality(development_bars, result.development)
    folds = [_fold_report(fold, result.symbol) for fold in result.folds]
    return {
        "schema_version": f"hip3_oil_shock_{mechanism}_development_v1",
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
        "development_folds": folds,
        "technical_path_evidence": path,
        "research_disposition": _disposition(result.development, result.folds, path),
        "out_of_sample_economics": result.out_of_sample_economics,
        "validation_accessed": False,
        "holdout_accessed": False,
        "limitations": _limitations(friction),
    }


def _strategy_identity(result: Hip3OilDevelopmentResult) -> dict[str, object]:
    return {
        "provider_id": result.proposed_provider_id,
        "profile_id": result.proposed_profile_id,
        "mechanism": _mechanism(result),
        "timeframe": "5m",
        "config": asdict(result.signal),
    }


def _mechanism(result: Hip3OilDevelopmentResult) -> str:
    for mechanism in ("reversion", "continuation"):
        token = f"_oil_shock_{mechanism}_"
        if token in result.proposed_provider_id and token in result.proposed_profile_id:
            return mechanism
    raise ValueError("oil strategy identity has an unsupported mechanism")


def _scaled_hypothesis(friction: Hip3OilFrictionContract) -> dict[str, float]:
    leverage = friction.execution.venue_max_leverage
    applied = min(5.0, leverage)
    return {
        "account_equity_usd": friction.scaled_equity_usd,
        "notional_usd": friction.scaled_notional_usd,
        "initial_margin_usd": friction.scaled_notional_usd / applied,
        "account_margin_fraction": (
            friction.scaled_notional_usd / applied / friction.scaled_equity_usd
        ),
        "leverage": applied,
    }


def _friction_contract(
    result: Hip3OilDevelopmentResult,
    friction: Hip3OilFrictionContract,
) -> dict[str, object]:
    nominal = hip3_oil_reversion_portfolio_config(
        result.execution, result.signal, stress=False
    )
    stress = hip3_oil_reversion_portfolio_config(
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
            "target_distance_bps": result.signal.target_bps,
            "stop_distance_bps": result.signal.stop_bps,
            "maximum_hold_bars": nominal.max_hold_bars,
            "maximum_hold_seconds": nominal.max_hold_seconds,
            "nominal_slippage_bps_per_side": nominal.entry_slippage_bps,
            "stress_slippage_bps_per_side": stress.entry_slippage_bps,
            "risk_high_column": nominal.risk_high_column,
            "risk_low_column": nominal.risk_low_column,
            "entry_risk_high_column": nominal.entry_risk_high_column,
            "entry_risk_low_column": nominal.entry_risk_low_column,
        },
    }


def _partition_economics(
    partition: MuPartitionResult, symbol: str
) -> dict[str, object]:
    return {
        "nominal": report_summary(
            partition.nominal, partition.start_utc, partition.end_utc, symbol=symbol
        ),
        "stress": report_summary(
            partition.stress, partition.start_utc, partition.end_utc, symbol=symbol
        ),
    }


def _fold_report(partition: MuPartitionResult, symbol: str) -> dict[str, object]:
    return {
        "name": partition.name,
        "window": _window(partition),
        **_partition_economics(partition, symbol),
    }


def _window(partition: MuPartitionResult) -> dict[str, str]:
    return {
        "start_utc": partition.start_utc.isoformat(),
        "end_utc": partition.end_utc.isoformat(),
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
    status = _status(checks)
    return {"status": status, "checks": checks, "live_change_proposed": False}


def _status(checks: dict[str, bool]) -> str:
    if not checks["technical_paths_resolved"]:
        return "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
    if not all(checks.values()):
        return "NOT_SUITABLE_DEVELOPMENT_ECONOMICS"
    return "DEVELOPMENT_SUPPORTED_REQUIRES_UNTOUCHED_OOS_AND_RUNTIME_PARITY"


def _limitations(friction: Hip3OilFrictionContract) -> list[str]:
    limitations = [
        "development evidence is hypothesis formation rather than out-of-sample",
        "validation and holdout economics were not evaluated",
        "BBO is exact while scaled depth impact is a distributional increment",
        "fee evidence uses current inputs rather than historical fee state",
        "visible depth excludes queue position and post-snapshot adverse selection",
        "no live strategy, asset, risk, sizing, or configuration change is authorized",
    ]
    if friction.live_stress_floor_bps_per_side is not None:
        limitations.append(
            f"live stress floor is the maximum absolute slippage from "
            f"{friction.live_slippage_observations} sparse mixed-strategy canary "
            "observations, not a stable distribution estimate"
        )
    return limitations
