"""Tests for Optuna/Karpathy autotuning module."""

from pathlib import Path
import pytest

from hypervector.sweep.autotune import run_optuna_autotune


def test_autotune_smoke(tmp_path: Path):
    # Run a fast autotune smoke test with n_trials=3
    res = run_optuna_autotune(
        strategy_name="crown_stack_long",
        symbol="BTC",
        timeframe="5m",
        lookback_days=180,
        n_trials=3,
        data_root=tmp_path,
        export_best=False,
    )
    assert res.strategy_name == "crown_stack_long"
    assert res.n_trials == 3
    assert "bbwp_lookback" in res.best_params or "st_atr" in res.best_params or res.best_params is not None
    assert res.board_path.is_file()
