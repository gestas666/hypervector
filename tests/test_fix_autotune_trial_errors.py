"""A technical failure aborts its own trial, never the measured search.

Regression tests: ``_TRIAL_ERRORS`` omitted IndexError, AttributeError and
AssertionError, and the regime tuner omitted ArithmeticError/RuntimeError, so
one bad trial aborted the search and discarded every completed measurement
without writing a board.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies import registry
from hypervector.strategies.registry import StrategySpec, register
from hypervector.sweep import autotune


class _CustomTechnicalFault(Exception):
    """A non-builtin failure type raised by a plugin strategy."""


@pytest.fixture
def faulty_strategy():
    names: list[str] = []

    def make(name: str, error: BaseException, fail_on_call: int) -> str:
        calls = {"n": 0}

        def build(df: pd.DataFrame, period: int = 5) -> tuple[pd.Series, pd.Series, str]:
            calls["n"] += 1
            if calls["n"] == fail_on_call:
                raise error
            entries = pd.Series(False, index=df.index)
            entries.iloc[period] = True
            return entries, pd.Series(False, index=df.index), "long"

        register(
            StrategySpec(
                name=name,
                role="uptrend",
                param_grid={"period": [3, 5, 8, 13]},
                build_signals=build,
            )
        )
        names.append(name)
        return name

    yield make
    for name in names:
        registry._REGISTRY.pop(name, None)


def _stub_history(monkeypatch: pytest.MonkeyPatch, n_bars: int = 120) -> None:
    bars = fixture_ohlcv(n_bars=n_bars)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))
    monkeypatch.setattr(
        autotune,
        "compute_trial_metrics",
        lambda close, entries, _exits, **_k: {
            "trade_count": int(entries.sum()),
            "sharpe": 1.0,
            "net_pnl": float(entries.to_numpy().argmax()),
            "total_return_pct": 0.0,
            "max_drawdown": -0.01,
        },
    )


@pytest.mark.parametrize(
    "error",
    [
        IndexError("iloc out of range"),
        AttributeError("'NoneType' object has no attribute 'shift'"),
        AssertionError("strategy invariant"),
        ZeroDivisionError("division by zero"),
        LookupError("missing lookup"),
        _CustomTechnicalFault("plugin fault"),
    ],
    ids=lambda error: type(error).__name__,
)
@pytest.mark.parametrize("sampler", ["karpathy", "optuna"])
def test_one_trial_failure_never_discards_the_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    faulty_strategy,
    error: Exception,
    sampler: str,
) -> None:
    name = faulty_strategy(f"test_fix_faulty_{sampler}_{type(error).__name__}", error, 3)
    _stub_history(monkeypatch)

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=name,
        n_trials=6,
        sampler=sampler,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    statuses = [trial["status"] for trial in board["all_trials"]]
    errors = [trial for trial in board["all_trials"] if trial["status"] == "error"]
    assert len(errors) == 1
    assert statuses.count("ok") == len(statuses) - 1 >= 1
    assert errors[0]["error_type"] == type(error).__name__
    assert errors[0]["error"] == f"{type(error).__name__}: {error}"
    assert board["error_trials"] == 1
    assert result.best_params


def test_operator_interrupt_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, faulty_strategy
) -> None:
    """Only Exception subclasses are trial failures; KeyboardInterrupt propagates."""
    name = faulty_strategy("test_fix_faulty_interrupt", KeyboardInterrupt(), 2)
    _stub_history(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name=name,
            n_trials=4,
            train_fraction=1.0,
            no_export=True,
        )


def test_all_failed_search_still_raises_with_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catching every Exception keeps the all-failed RuntimeError contract."""
    _stub_history(monkeypatch)

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise IndexError("systemic fault")

    monkeypatch.setattr(autotune, "compute_trial_metrics", fail)
    with pytest.raises(RuntimeError, match="no successful trials"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name="test_sma_cross_long",
            n_trials=3,
            train_fraction=1.0,
            no_export=True,
        )
    board_path = next((tmp_path / "logs/research").glob("autotune_*.json"))
    board = json.loads(board_path.read_text())
    assert {trial["error_type"] for trial in board["all_trials"]} == {"IndexError"}


def _regime_bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=300, freq="1min", tz="UTC")
    close = np.concatenate([np.linspace(100.0, 105.0, 150), np.linspace(105.0, 99.0, 150)])
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
        },
        index=index,
    )
