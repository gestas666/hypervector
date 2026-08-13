"""Contracts for causal, complete-journal Hulk Smash tuning."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.hulk_smash_autotune import (
    HulkAutotuneResult,
    HulkTuneFold,
    HulkTuneParameters,
    HulkTuneScenario,
    evaluate_hulk_autotune_results,
    rank_hulk_autotune_trials,
)
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
)
from hypervector.research.hulk_smash_autotune_journal import (
    HulkAutotuneJournal,
)
from hypervector.research.hulk_smash_autotune_surfaces import (
    development_folds_v1,
    local_signal_surface_v1,
    robust_development_scenarios_v1,
)


def _parameters(score: int) -> HulkTuneParameters:
    return HulkTuneParameters(
        supertrend_period=7,
        supertrend_multiplier=3.0,
        adx_period=20,
        squeeze_period=20,
        minimum_score=score,
        pivot_bars=8,
        adx_usable=18.0,
        adx_trending=25.0,
    )


def _result(
    parameters: HulkTuneParameters,
    fold: str,
    scenario: str,
    net: float,
) -> HulkAutotuneResult:
    return HulkAutotuneResult(
        trial_id=parameters.trial_id,
        fold=fold,
        scenario=scenario,
        signal_count=8,
        completed_trades=7,
        wins=4,
        losses=3,
        net_pnl_usd=net,
        profit_factor=1.2 if net > 0.0 else 0.8,
        maximum_drawdown_pct=2.0,
        fees_usd=15.0,
        funding_cashflow_usd=-1.0,
        liquidations=0,
        rejections=1,
    )


def test_ranking_retains_losing_trials_and_prefers_robust_cells() -> None:
    """Ranking rewards cross-cell stability without filtering observations."""
    stable = _parameters(8)
    brittle = _parameters(9)
    results = (
        _result(stable, "fold_1", "nominal", 10.0),
        _result(stable, "fold_1", "cost_stress", 1.0),
        _result(brittle, "fold_1", "nominal", 100.0),
        _result(brittle, "fold_1", "cost_stress", -1.0),
    )

    summaries = rank_hulk_autotune_trials((stable, brittle), results)

    assert [summary.trial_id for summary in summaries] == [
        stable.trial_id,
        brittle.trial_id,
    ]
    assert len(summaries) == 2
    assert summaries[1].positive_cells == 1
    assert summaries[1].worst_net_pnl_usd == -1.0


def test_journal_persists_every_result_and_rejects_duplicate_run(
    tmp_path: Path,
) -> None:
    """The append-only journal keeps losing cells and immutable run identity."""
    stable = _parameters(8)
    brittle = _parameters(9)
    results = (
        _result(stable, "fold_1", "nominal", 10.0),
        _result(brittle, "fold_1", "nominal", -5.0),
    )
    summaries = rank_hulk_autotune_trials((stable, brittle), results)
    path = tmp_path / "hulk_trials.duckdb"
    journal = HulkAutotuneJournal(path)

    journal.write_run(
        run_id="hulk-local-v1",
        surface="local_signal",
        source_identity={"bars_sha256": "abc"},
        parameters=(stable, brittle),
        results=results,
        summaries=summaries,
    )

    with duckdb.connect(str(path), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM hulk_autotune_trials"
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM hulk_autotune_results WHERE net_pnl_usd < 0"
        ).fetchone() == (1,)
    with pytest.raises(ValueError, match="already exists"):
        journal.write_run(
            run_id="hulk-local-v1",
            surface="local_signal",
            source_identity={"bars_sha256": "abc"},
            parameters=(stable, brittle),
            results=results,
            summaries=summaries,
        )


def test_result_matrix_must_be_complete() -> None:
    """Missing candidate results fail instead of producing a success-shaped rank."""
    with pytest.raises(ValueError, match="missing results"):
        rank_hulk_autotune_trials((_parameters(8), _parameters(9)), ())


def test_evaluator_retains_nominal_and_stressed_results() -> None:
    """Every declared fold/scenario cell reaches the friction-aware replay."""
    index = pd.date_range("2026-01-01", periods=4, freq="30min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.5, 100.7],
            "high": [100.1, 100.6, 100.8, 100.8],
            "low": [99.9, 99.9, 100.4, 100.6],
            "close": [100.0, 100.5, 100.7, 100.7],
            "funding_rate": [0.0, 0.0, 0.0, 0.0],
            "wave_cross": [0, 0, 0, 0],
        },
        index=index,
    )
    parameters = _parameters(8)
    signals = pd.DataFrame(
        [
            {
                "signal_time_utc": index[0],
                "symbol": "BTC",
                "candidate": parameters.trial_id,
                "side": "long",
                "score": 8,
                "stop_anchor": 99.99,
                "eligible": True,
            }
        ]
    )
    nominal = MarketCipherReplayConfig(initial_equity=15_000.0)
    stressed = MarketCipherReplayConfig(initial_equity=15_000.0, entry_slippage_bps=3.0)

    results = evaluate_hulk_autotune_results(
        bars_by_symbol={"BTC": bars},
        signals_by_trial={parameters.trial_id: signals},
        parameters=(parameters,),
        folds=(HulkTuneFold("fold_1", index[0], index[-1] + pd.Timedelta(minutes=30)),),
        scenarios=(
            HulkTuneScenario("nominal", nominal),
            HulkTuneScenario("cost_stress", stressed),
        ),
    )

    assert [result.scenario for result in results] == [
        "nominal",
        "cost_stress",
    ]
    assert all(result.completed_trades == 1 for result in results)
    assert results[1].net_pnl_usd < results[0].net_pnl_usd


def test_local_surface_and_development_protocol_are_frozen() -> None:
    """The first stable-neighborhood search is declared before evaluation."""
    surface = local_signal_surface_v1()

    assert len(surface) == 27
    assert len({trial.trial_id for trial in surface}) == 27
    assert any(
        trial.minimum_score == 8
        and trial.pivot_bars == 8
        and trial.adx_usable == 18.0
        and trial.adx_trending == 25.0
        for trial in surface
    )
    assert [fold.name for fold in development_folds_v1()] == [
        "development_1",
        "development_2",
        "development_3",
    ]
    assert [scenario.name for scenario in robust_development_scenarios_v1()] == [
        "nominal",
        "cost_stress",
        "entry_delay_2_bars",
    ]
