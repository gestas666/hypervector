"""Autotuning must distinguish failed computation from weak measured results."""

from pathlib import Path

import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.registry import ExecutionProfile
from hypervector.sweep import autotune


@pytest.mark.parametrize("trials", [0, -1])
def test_invalid_trial_count_fails_before_data_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trials: int
) -> None:
    """An impossible search request must not trigger acquisition."""
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("read before trial validation"),
    )
    with pytest.raises(ValueError, match="positive"):
        autotune.run_autotune(data_root=tmp_path, n_trials=trials)


def test_all_technical_failures_preserve_board_and_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed search cannot look like a successful empty result or export."""
    bars = fixture_ohlcv(n_bars=100)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected metrics fault")

    monkeypatch.setattr(autotune, "compute_trial_metrics", fail)
    with pytest.raises(RuntimeError, match="no successful trials"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name="test_sma_cross_long",
            n_trials=2,
            no_export=True,
        )
    import json

    board = json.loads(
        next((tmp_path / "logs/research").glob("autotune_*.json")).read_text()
    )
    assert len(board["all_trials"]) == 2
    assert all(trial["status"] == "error" for trial in board["all_trials"])
    assert not (tmp_path / "exports").exists()


def test_negative_valid_trials_remain_eligible_for_adaptation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only technical failure excludes an elite, without an implicit score cutoff."""
    bars = fixture_ohlcv(n_bars=100)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))
    monkeypatch.setattr(
        autotune,
        "compute_trial_metrics",
        lambda *_a, **_k: {
            "trade_count": 0,
            "sharpe": -100.0,
            "net_pnl": -100.0,
            "max_drawdown": 90.0,
        },
    )
    mutated: list[bool] = []
    original = autotune._mutate_grid_params

    def mutate(*args: object) -> dict[str, object]:
        mutated.append(True)
        return original(*args)

    monkeypatch.setattr(autotune, "_mutate_grid_params", mutate)
    result = autotune.run_autotune(
        data_root=tmp_path, strategy_name="test_sma_cross_long", n_trials=10, no_export=True
    )
    assert result.best_metrics["net_pnl"] == -100.0
    assert mutated


def test_optuna_bounds_are_exact_points_on_their_declared_grid() -> None:
    """Search bounds must not rely on Optuna silently shrinking a range."""
    import math

    class StrictTrial:
        def suggest_categorical(self, _name: str, choices: list[object]) -> object:
            return choices[0]

        def suggest_float(
            self, _name: str, low: float, high: float, *, step: float
        ) -> float:
            assert math.isclose((high - low) / step, round((high - low) / step))
            return low

    autotune._optuna_exit_dict(StrictTrial(), execution=ExecutionProfile())
