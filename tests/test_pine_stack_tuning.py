"""Bounded development-only tuning tests for the four-Pine stack."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_tuning import (
    PineStackTuningConfig,
    PineStackTuningResult,
    declared_entry_parameter_grid,
    declared_final_development_grid,
    declared_pseudo_holdout_grid,
    declared_post_hoc_exit_grid,
    declared_risk_parameter_grid,
    declared_tp_axis_threshold_grid,
    declared_tp_parameter_grid,
    evaluate_pine_stack_tuning_trial,
    rank_pine_stack_tuning_results,
)


def _bars(rows: int = 500) -> pd.DataFrame:
    """Return deterministic 30m waves with zero funding."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 7.0 * np.sin(positions / 10.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="30min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.6,
            "low": np.minimum(open_, close) - 0.6,
            "close": close,
            "volume": 200.0 + positions,
            "funding_rate": np.zeros(rows),
        }
    )


def test_entry_grid_is_bounded_unique_and_retains_source_control() -> None:
    """Development tuning must use the predeclared 27-neighbor surface."""
    grid = declared_entry_parameter_grid()

    assert len(grid) == 27
    assert len(set(grid)) == 27
    assert (
        PineStackTuningConfig(
            cs_atr_period=10,
            cs_sensitivity=5.0,
            trend_lookback=30,
        )
        in grid
    )
    assert {trial.cs_atr_period for trial in grid} == {7, 10, 14}
    assert {trial.cs_sensitivity for trial in grid} == {3.0, 5.0, 8.0}
    assert {trial.trend_lookback for trial in grid} == {20, 30, 48}


def test_risk_grid_changes_only_stop_and_hold_around_entry_control() -> None:
    """Risk tuning must not reopen the already selected entry dimensions."""
    grid = declared_risk_parameter_grid()

    assert len(grid) == 9
    assert len(set(grid)) == 9
    assert {trial.stop_margin_pct for trial in grid} == {5.0, 10.0, 15.0}
    assert {trial.maximum_hold_hours for trial in grid} == {4, 8, 16}
    assert {
        (trial.cs_atr_period, trial.cs_sensitivity, trial.trend_lookback)
        for trial in grid
    } == {(10, 5.0, 30)}


def test_tp_grid_retains_flip_control_and_bounds_density_support() -> None:
    """TP tuning changes only declared density parameters around the core."""
    grid = declared_tp_parameter_grid()

    assert len(grid) == 9
    assert len(set(grid)) == 9
    assert sum(trial.tp_exit_threshold is None for trial in grid) == 1
    challengers = [trial for trial in grid if trial.tp_exit_threshold is not None]
    assert {trial.tp_pivot_width for trial in challengers} == {3, 5}
    assert {trial.tp_bin_count for trial in challengers} == {5, 10}
    assert {trial.tp_minimum_directional_pool for trial in challengers} == {25, 50}
    assert {trial.tp_exit_threshold for trial in challengers} == {80}


def test_tp_axis_grid_challenges_time_axis_and_threshold_only() -> None:
    """TP semantic tuning keeps the support winner fixed and retains control."""
    grid = declared_tp_axis_threshold_grid()

    assert len(grid) == 5
    assert sum(trial.tp_exit_threshold is None for trial in grid) == 1
    challengers = [trial for trial in grid if trial.tp_exit_threshold is not None]
    assert {trial.tp_pivot_width for trial in challengers} == {5}
    assert {trial.tp_bin_count for trial in challengers} == {5}
    assert {trial.tp_minimum_directional_pool for trial in challengers} == {50}
    assert {trial.tp_include_time_of_day for trial in challengers} == {True, False}
    assert {trial.tp_exit_threshold for trial in challengers} == {80, 100}


def test_final_development_grid_is_frozen_two_by_two_interaction() -> None:
    """The final development check crosses only exit and hold semantics."""
    grid = declared_final_development_grid()

    assert len(grid) == 4
    assert {trial.maximum_hold_hours for trial in grid} == {4, 8}
    assert {trial.tp_exit_threshold for trial in grid} == {None, 80}
    tp_trials = [trial for trial in grid if trial.tp_exit_threshold == 80]
    assert all(not trial.tp_include_time_of_day for trial in tp_trials)
    assert all(trial.tp_pivot_width == 5 for trial in tp_trials)
    assert all(trial.tp_minimum_directional_pool == 50 for trial in tp_trials)


def test_pseudo_holdout_grid_contains_only_validation_winner() -> None:
    """Pseudo-holdout cannot compare a new or validation-losing identity."""
    grid = declared_pseudo_holdout_grid()

    assert len(grid) == 1
    assert grid[0] == PineStackTuningConfig(10, 5.0, 30)


def test_post_hoc_exit_grid_changes_only_open_position_exit_policy() -> None:
    """The contaminated diagnostic retains an exact source control."""
    grid = declared_post_hoc_exit_grid()

    assert len(grid) == 2
    assert {trial.exit_policy for trial in grid} == {"cs_flip", "max_hold_only"}
    assert all(trial.maximum_hold_hours == 8 for trial in grid)
    assert all(trial.stop_margin_pct == 10.0 for trial in grid)


def test_tuning_trial_is_report_only_and_uses_completed_native_signals() -> None:
    """A tuning cell must share portfolio friction without execution authority."""
    bars = _bars()
    result = evaluate_pine_stack_tuning_trial(
        feature_bars=bars.drop(columns="funding_rate"),
        scored_bars=bars,
        symbol="ETH",
        venue_max_leverage=25.0,
        bar_minutes=30,
        config=PineStackTuningConfig(
            cs_atr_period=10,
            cs_sensitivity=5.0,
            trend_lookback=20,
            maximum_hold_hours=4,
        ),
    )

    assert result.signal_count > 0
    assert result.completed_trades > 0
    assert result.execution_authority == "none"
    assert result.config.maximum_hold_hours == 4
    assert result.total_fees_usd > 0.0


def _result(
    config: PineStackTuningConfig,
    net_pnl_usd: float,
    monthly: dict[str, float],
) -> PineStackTuningResult:
    """Return a compact result for stability-ranking tests."""
    return PineStackTuningResult(
        config=config,
        symbol="ETH",
        bar_minutes=30,
        signal_count=10,
        completed_trades=8,
        wins=5,
        losses=3,
        net_pnl_usd=net_pnl_usd,
        profit_factor=1.2 if net_pnl_usd > 0.0 else 0.8,
        maximum_drawdown_pct=4.0,
        total_fees_usd=12.0,
        funding_cashflow_usd=-1.0,
        liquidations=0,
        monthly_net_pnl_usd=monthly,
        trade_records=(),
    )


def test_ranking_prefers_stable_neighbors_and_retains_losing_trials() -> None:
    """Tuning ranks robustness without dropping negative observations."""
    left = PineStackTuningConfig(7, 5.0, 30)
    center = PineStackTuningConfig(10, 5.0, 30)
    isolated = PineStackTuningConfig(14, 8.0, 48)
    losing = PineStackTuningConfig(14, 3.0, 20)
    results = (
        _result(left, 50.0, {"2025-08": 25.0, "2025-09": 25.0}),
        _result(center, 70.0, {"2025-08": 30.0, "2025-09": 40.0}),
        _result(isolated, 500.0, {"2025-08": 500.0, "2025-09": -1.0}),
        _result(losing, -10.0, {"2025-08": -5.0, "2025-09": -5.0}),
    )

    summaries = rank_pine_stack_tuning_results(results)

    assert summaries[0].trial_id == center.trial_id
    assert len(summaries) == 4
    assert summaries[-1].net_pnl_usd == -10.0
    assert (
        next(
            value for value in summaries if value.trial_id == isolated.trial_id
        ).positive_neighbors
        == 0
    )
