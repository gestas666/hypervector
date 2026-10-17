"""Autotune searches, ranks and exports by one objective over a chronological split.

Regression tests for the autotune review findings:
- the search maximised ``sharpe + net_pnl/1000`` while the export picked ``net_pnl``;
- zero-trade winners were not reported;
- the opt-in drawdown penalty compared a negative fraction against 25.0;
- exported ``best_metrics`` were the in-sample maximum over every trial.
"""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies import registry
from hypervector.strategies.registry import StrategySpec, register
from hypervector.sweep import autotune, autotune_evaluation

# arm -> (trade_count, sharpe, net_pnl)
_ARMS = {
    0: (4, 50.0, -30.0),  # best "score", worst net
    1: (6, -40.0, -5.0),  # best net among trading arms
    2: (0, 0.0, 0.0),  # never trades: undefined Sharpe reported as 0.0
}


@pytest.fixture
def arm_strategy():
    """Register a three-arm fake strategy whose metrics are chosen per arm."""
    names: list[str] = []

    def make(name: str, grid: dict[str, list[object]] | None = None) -> str:
        def build(df: pd.DataFrame, arm: int = 0) -> tuple[pd.Series, pd.Series, str]:
            entries = pd.Series(False, index=df.index, name=f"arm{arm}")
            return entries, pd.Series(False, index=df.index), "long"

        register(
            StrategySpec(
                name=name,
                role="uptrend",
                param_grid=grid or {"arm": [0, 1, 2]},
                build_signals=build,
            )
        )
        names.append(name)
        return name

    yield make
    for name in names:
        registry._REGISTRY.pop(name, None)


def _arm_metrics(entries: pd.Series, close: pd.Series) -> dict[str, object]:
    arm = int(str(entries.name).removeprefix("arm"))
    trades, sharpe, net = _ARMS[arm]
    return {
        "trade_count": trades,
        "sharpe": sharpe,
        "net_pnl": net,
        "total_return_pct": net / 100.0,
        "max_drawdown": -0.9,
        "exit_mode": "atr",
        "first_index": int(close.index[0]),
        "bars": len(close),
    }


_LABELS = ("evaluation_window", "selection_basis")


def _unlabelled(metrics: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in metrics.items() if key not in _LABELS}


def _install(monkeypatch: pytest.MonkeyPatch, bars: pd.DataFrame) -> list[int]:
    """Stub history and metrics; cycle the coarse sample through every arm."""
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: (bars, {"sources": {"fixture": len(bars)}}),
    )
    monkeypatch.setattr(
        autotune,
        "compute_trial_metrics",
        lambda close, entries, _exits, **_k: _arm_metrics(entries, close),
    )
    counter = {"n": 0}
    original_sample = autotune._sample_grid_params

    def cycle(rng: object, grid: dict[str, list[object]]) -> dict[str, object]:
        sampled = original_sample(rng, grid)
        if "arm" in grid:
            sampled["arm"] = grid["arm"][counter["n"] % len(grid["arm"])]
            counter["n"] += 1
        return sampled

    monkeypatch.setattr(autotune, "_sample_grid_params", cycle)
    returned: list[float] = []
    original_evaluate = autotune_evaluation.TrialEvaluator.evaluate

    def recording(self, params, exits, number):  # type: ignore[no-untyped-def]
        value = original_evaluate(self, params, exits, number)
        returned.append(value)
        return value

    monkeypatch.setattr(autotune_evaluation.TrialEvaluator, "evaluate", recording)
    return returned  # type: ignore[return-value]


@pytest.mark.parametrize(
    ("objective", "expected_arm"),
    [("score", 0), ("net_pnl", 2), ("sharpe", 0)],
)
def test_search_ranking_and_export_share_one_objective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm_strategy,
    objective: str,
    expected_arm: int,
) -> None:
    """The value the search maximises is the value that picks the export."""
    name = arm_strategy(f"test_fix_arms_{objective}")
    returned = _install(monkeypatch, fixture_ohlcv(n_bars=120))

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=5,
        objective=objective,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    ok = [trial for trial in board["all_trials"] if trial["status"] == "ok"]
    assert len(ok) == 5
    for trial, value in zip(ok, returned):
        expected = autotune_evaluation.objective_value(trial["metrics"], objective)
        assert value == expected
        stored = trial["objective_value"]
        assert stored == (expected if expected != float("-inf") else None)
    assert result.best_params["arm"] == expected_arm
    assert board["objective"] == objective
    assert result.objective == objective


def test_zero_trade_winner_is_reported_not_gated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arm_strategy,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When every trading config loses, the inactive one wins and is flagged."""
    name = arm_strategy("test_fix_arms_zero_trade")
    _install(monkeypatch, fixture_ohlcv(n_bars=120))
    caplog.set_level("WARNING", logger="hypervector.sweep.autotune_artifacts")

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=5,
        train_fraction=1.0,
    )

    board = json.loads(result.board_path.read_text())
    assert result.objective == "net_pnl"
    assert result.best_params["arm"] == 2
    assert result.best_trade_count == 0
    assert board["best_trade_count"] == 0
    assert board["zero_trade_trials"] == 1
    assert any("zero trades" in warning for warning in result.warnings)
    assert board["warnings"] == result.warnings
    # The CLI prints only the result JSON; warnings must reach stderr too.
    logged = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("selected trial has zero trades" in message for message in logged)
    flags = {
        trial["params"]["arm"]: trial["sharpe_defined"] for trial in board["all_trials"]
    }
    assert flags == {0: True, 1: True, 2: False}
    # Reported, never gated: the export is still written.
    assert result.export_dir is not None and result.export_dir.is_dir()


def test_sharpe_objective_ranks_undefined_sharpe_below_defined() -> None:
    """A zero-trade Sharpe of 0.0 is undefined and must not beat a real -3.0."""
    undefined = {"trade_count": 0, "sharpe": 0.0, "net_pnl": 0.0}
    defined = {"trade_count": 2, "sharpe": -3.0, "net_pnl": -40.0}
    value = autotune_evaluation.objective_value
    assert value(defined, "sharpe") > value(undefined, "sharpe")
    assert value(undefined, "net_pnl") > value(defined, "net_pnl")
    with pytest.raises(ValueError, match="objective"):
        value(defined, "calmar")


def test_drawdown_penalty_path_is_removed_and_score_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dead opt-in penalty compared -0.9 with 25.0; it no longer exists."""
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read with a removed option"),
    )
    metrics = {"trade_count": 2, "sharpe": 1.5, "net_pnl": 250.0, "max_drawdown": -0.9}
    assert autotune_evaluation.objective_value(metrics, "score") == 1.5 + 250.0 / 1000.0
    names = {item.name for item in fields(autotune_evaluation.TrialEvaluator)}
    assert "apply_penalties" not in names
    with pytest.raises(TypeError):
        autotune.run_autotune(data_root=tmp_path, apply_penalties=True)  # type: ignore[call-arg]


def test_selection_is_train_only_and_exported_metrics_are_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_strategy
) -> None:
    """Search trials see only the training slice; the winner is re-measured once."""
    name = arm_strategy("test_fix_arms_holdout")
    bars = fixture_ohlcv(n_bars=200)
    _install(monkeypatch, bars)
    seen_lengths: list[int] = []
    spec = registry.get_strategy(name)
    original_build = spec.build_signals

    def build(df: pd.DataFrame, **params: object) -> tuple[pd.Series, pd.Series, str]:
        seen_lengths.append(len(df))
        return original_build(df, **params)

    spec.build_signals = build

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=5,
        train_fraction=0.75,
    )

    board = json.loads(result.board_path.read_text())
    # Five search trials on the 150-bar training slice, one holdout pass that
    # builds signals on all 200 bars (causal warmup) and scores bars 150..199,
    # then one report-only full-window re-measure (engine parity) of the winner.
    assert seen_lengths[:5] == [150] * 5
    assert seen_lengths[5:] == [200, 200]
    assert board["best_full_window_metrics"]["bars"] == 200
    assert board["best_full_window_metrics"]["first_index"] == 0
    assert all(
        trial["metrics"]["bars"] == 150 and trial["metrics"]["first_index"] == 0
        for trial in board["all_trials"]
    )
    assert result.selection_basis == "train_only"
    assert result.holdout_metrics is not None
    assert result.holdout_metrics["first_index"] == 150
    assert result.holdout_metrics["bars"] == 50
    assert _unlabelled(result.best_metrics) == result.holdout_metrics
    # The result (and so the CLI JSON) says which window it reports.
    assert result.best_metrics["evaluation_window"] == "holdout"
    assert result.best_metrics["selection_basis"] == "train_only"
    assert result.train_metrics["bars"] == 150
    assert board["selection_basis"] == "train_only"
    assert board["best_train_metrics"] == result.train_metrics
    assert board["best_holdout_metrics"] == result.holdout_metrics
    assert board["train_window"]["bar_count"] == 150
    assert board["holdout_window"]["bar_count"] == 50
    metrics = json.loads((result.export_dir / "metrics.json").read_text())
    assert metrics["evaluation_window"] == "holdout"
    assert metrics["selection_basis"] == "train_only"
    assert metrics["bars"] == 50
    meta = json.loads((result.export_dir / "meta.json").read_text())
    assert meta["evaluation"]["train_metrics"]["bars"] == 150
    assert meta["evaluation"]["holdout_metrics"]["bars"] == 50


def test_full_window_fraction_keeps_the_in_sample_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_strategy
) -> None:
    """train_fraction=1.0 is the explicit, labelled in-sample mode."""
    name = arm_strategy("test_fix_arms_in_sample")
    _install(monkeypatch, fixture_ohlcv(n_bars=120))

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=3,
        train_fraction=1.0,
        no_export=True,
    )

    assert result.selection_basis == "full_window_in_sample"
    assert result.holdout_metrics is None
    assert _unlabelled(result.best_metrics) == result.train_metrics
    assert result.best_metrics["evaluation_window"] == "full_window_in_sample"


@pytest.mark.parametrize("fraction", [0.0, -0.2, 1.5, float("nan")])
def test_invalid_train_fraction_fails_before_data_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fraction: float
) -> None:
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read before fraction validation"),
    )
    with pytest.raises(ValueError, match="train_fraction"):
        autotune.run_autotune(data_root=tmp_path, train_fraction=fraction)


def test_holdout_slice_too_small_is_a_parameter_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_strategy
) -> None:
    name = arm_strategy("test_fix_arms_tiny_holdout")
    _install(monkeypatch, fixture_ohlcv(n_bars=40))
    with pytest.raises(ValueError, match="holdout"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name=name,
            n_trials=2,
            train_fraction=0.99,
            no_export=True,
        )


def test_holdout_technical_failure_keeps_the_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_strategy
) -> None:
    """A failed holdout measurement is recorded; the measured search survives."""
    name = arm_strategy("test_fix_arms_holdout_failure")
    bars = fixture_ohlcv(n_bars=200)
    _install(monkeypatch, bars)

    def metrics(close, entries, _exits, **_k):  # type: ignore[no-untyped-def]
        if int(close.index[0]) > 0:
            raise IndexError("injected holdout fault")
        return _arm_metrics(entries, close)

    monkeypatch.setattr(autotune, "compute_trial_metrics", metrics)
    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=3,
        train_fraction=0.75,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    assert result.holdout_metrics is None
    assert board["holdout_error"].startswith("IndexError: injected holdout fault")
    assert _unlabelled(result.best_metrics) == result.train_metrics
    assert result.best_metrics["evaluation_window"] == "train_in_sample"
    assert result.selection_basis == "train_only"
    assert any("holdout" in warning for warning in result.warnings)
