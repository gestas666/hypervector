"""Immutable report contract for exact deployed HIP-3 lifecycle diagnostics."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import pytest

from hypervector.live.hip3_cohort_providers import HIP3_BREAKOUT_INDEX_STRATEGY
from hypervector.live.hip3_provider_recipes import configured_hip3_recipe
from hypervector.research.hip3_deployed_lifecycle import (
    Hip3DeployedLifecycleSpec,
    deployed_lifecycle_signals,
    evaluate_deployed_lifecycle,
)
from hypervector.research.hip3_deployed_lifecycle_reporting import (
    deployed_lifecycle_case_report,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)


def _case_inputs() -> tuple[
    dict[str, object],
    Hip3TransferAsset,
    Hip3ExecutionFriction,
    Hip3TransferWindows,
]:
    index = pd.date_range("2026-01-01", periods=12, freq="15min", tz="UTC")
    close = [100.0, 100.0, 100.5, 100.8, 100.2, 99.8] * 2
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": close,
            "entry_bid": [value - 0.01 for value in close],
            "entry_ask": [value + 0.01 for value in close],
            "decision_bid": [value - 0.01 for value in close],
            "decision_ask": [value + 0.01 for value in close],
            "gap_before_bars": [0] * 12,
            "funding_rate": [0.0] * 12,
        },
        index=index,
    )
    asset = Hip3TransferAsset("xyz:SP500", 50.0, bars)
    friction = Hip3ExecutionFriction(75.0, 0.00001, 1.0, 0.0, 5.0, 2.0)
    windows = Hip3TransferWindows(
        index[0],
        index[4],
        index[8],
        index[-1] + pd.Timedelta(minutes=15),
        ((index[0], index[4]),),
    )
    recipe = configured_hip3_recipe(HIP3_BREAKOUT_INDEX_STRATEGY)
    source = {
        "schema_version": "hip3_breakout_pressure_transfer_v1",
        "symbols": [asset.symbol],
        "selected_config": asdict(recipe),
        "execution_authority": "none",
        "holdout": {"status": "sealed_not_evaluated", "metrics_accessed": False},
        "validation": {
            "nominal": [
                {
                    "symbol": asset.symbol,
                    "completed_trades": 2,
                    "net_pnl_usd": -1.0,
                    "profit_factor": 0.5,
                }
            ],
            "stress": [
                {
                    "symbol": asset.symbol,
                    "completed_trades": 2,
                    "net_pnl_usd": -1.5,
                    "profit_factor": 0.4,
                }
            ],
        },
    }
    return source, asset, friction, windows


def _cells(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    windows: Hip3TransferWindows,
):
    signals = pd.DataFrame(
        {
            "long_entry": [True] + [False] * 11,
            "short_entry": [False] * 12,
            "long_exit": [False] * 12,
            "short_exit": [False] * 12,
        },
        index=asset.bars.index,
    )
    return evaluate_deployed_lifecycle(
        asset,
        friction,
        deployed_lifecycle_signals(signals),
        windows,
    )


def test_case_report_proves_recipe_parity_and_keeps_holdout_sealed() -> None:
    source, asset, friction, windows = _case_inputs()
    recipe = configured_hip3_recipe(HIP3_BREAKOUT_INDEX_STRATEGY)

    report = deployed_lifecycle_case_report(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        source_report=source,
        source_evidence={"path": "source.json", "sha256": "abc", "bytes": 1},
        production_recipe=recipe,
        cells=_cells(asset, friction, windows),
        windows=windows,
    )

    assert report["recipe_parity"]["exact_match"] is True
    assert report["execution_authority"] == "none"
    assert report["holdout"]["metrics_accessed"] is False
    assert report["holdout"]["status"] == "sealed_not_evaluated"
    comparison = report["validation_comparison"]["nominal"][asset.symbol]
    assert comparison["prior_modeled_lifecycle"]["net_pnl_usd"] == -1.0
    assert comparison["deployed_lifecycle"]["completed_trades"] >= 0
    assert comparison["delta"]["net_pnl_usd"] == pytest.approx(
        comparison["deployed_lifecycle"]["net_pnl_usd"] + 1.0
    )


def test_case_report_rejects_source_recipe_drift() -> None:
    source, asset, friction, windows = _case_inputs()
    source["selected_config"] = {"breakout_lookback_bars": 999}

    with pytest.raises(ValueError, match="does not match production recipe"):
        deployed_lifecycle_case_report(
            strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
            source_report=source,
            source_evidence={"path": "source.json", "sha256": "abc", "bytes": 1},
            production_recipe=configured_hip3_recipe(HIP3_BREAKOUT_INDEX_STRATEGY),
            cells=_cells(asset, friction, windows),
            windows=windows,
        )


def test_case_report_serializes_early_adverse_exit_contract() -> None:
    source, asset, friction, windows = _case_inputs()
    recipe = configured_hip3_recipe(HIP3_BREAKOUT_INDEX_STRATEGY)
    spec = Hip3DeployedLifecycleSpec(signal_exit_policy="early_adverse")
    signals = pd.DataFrame(
        {
            "long_entry": [True] + [False] * 11,
            "short_entry": [False] * 12,
            "long_exit": [False] * 12,
            "short_exit": [False] * 12,
        },
        index=asset.bars.index,
    )
    cells = evaluate_deployed_lifecycle(
        asset,
        friction,
        signals,
        windows,
        spec=spec,
    )

    report = deployed_lifecycle_case_report(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        source_report=source,
        source_evidence={"path": "source.json", "sha256": "abc", "bytes": 1},
        production_recipe=recipe,
        cells=cells,
        windows=windows,
        spec=spec,
    )

    contract = report["bar_diagnostic_contract"]
    assert contract["signal_exit_policy"] == "early_adverse"
    assert contract["signal_exit_max_age_bars"] == 8
    assert contract["signal_exit_max_mfe_bps"] == 20.0
    assert contract["signal_exit_min_adverse_bps"] == 13.0
