"""The autotune search space must be real: book dimensions, mutation and dedupe.

Regression tests:
- Optuna added book_gate/max_spread_bps/min_obi for every strategy whenever a
  book path was given, so 14 strategies failed every trial with TypeError, and a
  missing book file was silently ignored;
- the Karpathy adaptive phase only moved float grid values and ``sl_atr_mult``,
  never deduplicated, and a declared leverage above a symbol's venue cap failed
  every trial only after the whole search had run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import (
    ExecutionProfile,
    StrategySpec,
    get_strategy,
    register,
)
from hypervector.sweep import autotune, autotune_search
from hypervector.sweep.autotune_evaluation import TrialEvaluator
from hypervector.sweep.autotune_sampling import strategy_managed_exit_dict
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.metrics import compute_trial_metrics
from synthetic_strategies import (
    MANAGED_EXECUTION,
    MANAGED_LONG,
    SYNTHETIC_LONG,
    SYNTHETIC_SHORT,
    sma_cross_signals,
)

_BOOK_KEYS = {"book_gate", "max_spread_bps", "min_obi"}
_BOOK_STRATEGIES = {SYNTHETIC_LONG, SYNTHETIC_SHORT}
_NO_BOOK_LONG = "test_no_book_long"
_SINGLE_MANAGED = "test_single_managed_long"
_HIGH_LEVERAGE = "test_high_leverage_long"


@pytest.fixture(autouse=True)
def _local_specs() -> None:
    """Specs this module needs beyond the shared synthetic family."""

    def no_book(df: pd.DataFrame, fast: int = 5, slow: int = 20):
        return sma_cross_signals(df, fast=fast, slow=slow, direction="long")

    register(
        StrategySpec(
            name=_NO_BOOK_LONG,
            role="uptrend",
            param_grid={"fast": [5, 10], "slow": [20, 30]},
            build_signals=no_book,
        )
    )
    register(
        StrategySpec(
            name=_SINGLE_MANAGED,
            role="uptrend",
            param_grid={"fast": [5], "slow": [20]},
            build_signals=no_book,
            execution=MANAGED_EXECUTION,
        )
    )
    register(
        StrategySpec(
            name=_HIGH_LEVERAGE,
            role="uptrend",
            param_grid={"fast": [5], "slow": [20]},
            build_signals=no_book,
            execution=ExecutionProfile(
                fixed_margin_fraction=0.7, leverage=30.0, strategy_managed_exits=True
            ),
        )
    )


def _stub_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        autotune,
        "compute_trial_metrics",
        lambda *_a, **_k: {
            "trade_count": 1,
            "sharpe": 0.5,
            "net_pnl": 1.0,
            "total_return_pct": 0.01,
            "max_drawdown": -0.01,
        },
    )


def test_missing_book_file_fails_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read before book path validation"),
    )
    with pytest.raises(FileNotFoundError, match="book data path"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name=SYNTHETIC_LONG,
            book_data_path=tmp_path / "missing.jsonl",
        )


def test_book_gate_capability_is_declared_only_where_builders_gate() -> None:
    register_all_strategies()
    from hypervector.strategies.registry import list_strategies

    declared = {spec.name for spec in list_strategies() if spec.supports_book_gate}
    assert declared == _BOOK_STRATEGIES


class _RecordingTrial:
    number = 0

    def __init__(self) -> None:
        self.names: list[str] = []

    def suggest_categorical(self, name: str, choices: list[object]) -> object:
        self.names.append(name)
        return choices[0]

    def suggest_float(self, name: str, low: float, _high: float, *, step: float) -> float:
        del step
        self.names.append(name)
        return low


@pytest.mark.parametrize(
    ("strategy", "columns", "book_path", "expected"),
    [
        (_NO_BOOK_LONG, True, "book.jsonl", False),
        (MANAGED_LONG, True, "book.jsonl", False),
        (SYNTHETIC_LONG, True, "book.jsonl", True),
        (SYNTHETIC_LONG, False, "book.jsonl", False),
        (SYNTHETIC_SHORT, True, None, True),
    ],
)
def test_optuna_book_dimensions_need_support_and_aligned_columns(
    strategy: str, columns: bool, book_path: str | None, expected: bool
) -> None:
    register_all_strategies()
    bars = fixture_ohlcv(n_bars=40)
    if columns:
        bars = bars.assign(spread_bps=1.0, obi_5=0.1)
    captured: dict[str, object] = {}
    evaluator = SimpleNamespace(
        strategy=get_strategy(strategy),
        execution=get_strategy(strategy).execution,
        bars=bars,
        evaluate=lambda params, exits, number: captured.update(params) or 0.0,
    )
    settings = SimpleNamespace(symbol="BTC", book_data_path=book_path)
    tools = SimpleNamespace(
        clamp=lambda params, _symbol: params,
        optuna_exits=lambda _trial, execution: {"mode": "atr"},
    )
    trial = _RecordingTrial()

    autotune_search.optuna_objective(settings, evaluator, tools, trial)

    assert (_BOOK_KEYS <= set(captured)) is expected
    assert (_BOOK_KEYS <= set(trial.names)) is expected


def test_optuna_with_book_data_runs_for_a_strategy_without_book_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A builder that rejects book kwargs must never be handed them."""
    import hypervector.data.book_align as book_align

    bars = fixture_ohlcv(n_bars=160, drift=1.0)
    book = tmp_path / "book.jsonl"
    book.write_text("{}\n")
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))
    monkeypatch.setattr(book_align, "load_l2_jsonl", lambda _path: pd.DataFrame())
    monkeypatch.setattr(
        book_align,
        "align_orderbook_to_ohlcv",
        lambda frame, _book: frame.assign(spread_bps=1.0, obi_5=0.0),
    )
    _stub_metrics(monkeypatch)

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=_NO_BOOK_LONG,
        sampler="optuna",
        n_trials=3,
        book_data_path=book,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    assert [trial["status"] for trial in board["all_trials"]] == ["ok"] * 3
    assert all(not (_BOOK_KEYS & set(trial["params"])) for trial in board["all_trials"])
    assert board["book_data_loaded"] is True
    assert board["search_space"]["book_dimensions"] is False
    assert any("book" in warning for warning in result.warnings)


class _StepRng:
    """Always step (uniform returns its low bound) toward the last neighbour."""

    def integers(self, _low: int, high: int) -> int:
        return high - 1

    def uniform(self, low: float, _high: float) -> float:
        return low


def test_int_params_step_to_a_neighbouring_grid_index() -> None:
    grid = {"period": [5, 10, 20, 40]}
    assert autotune._mutate_grid_params(_StepRng(), {"period": 10}, grid) == {"period": 20}
    assert autotune._mutate_grid_params(_StepRng(), {"period": 40}, grid) == {"period": 20}
    rng = np.random.default_rng(0)
    seen = [
        autotune._mutate_grid_params(rng, {"period": 10}, grid)["period"]
        for _ in range(200)
    ]
    assert set(seen) == {5, 10, 20}
    assert all(type(value) is int for value in seen)


def test_bool_and_categorical_params_switch_with_probability() -> None:
    grid = {"enabled": [True, False], "mode": ["a", "b", "c"]}
    rng = np.random.default_rng(1)
    draws = [
        autotune._mutate_grid_params(rng, {"enabled": True, "mode": "a"}, grid)
        for _ in range(300)
    ]
    enabled = {draw["enabled"] for draw in draws}
    modes = {draw["mode"] for draw in draws}
    assert enabled == {True, False}
    assert modes == {"a", "b", "c"}
    assert all(type(draw["enabled"]) is bool for draw in draws)
    unchanged = sum(draw == {"enabled": True, "mode": "a"} for draw in draws)
    assert 0 < unchanged < len(draws)


@pytest.mark.parametrize(
    ("mode", "moving"),
    [
        ("fixed_rr", {"sl_pct", "rr"}),
        ("atr", {"sl_atr_mult", "rr"}),
        ("trail", {"trail_atr_mult"}),
    ],
)
def test_exit_mutation_moves_the_fields_the_mode_uses(mode: str, moving: set[str]) -> None:
    elite = {
        "mode": mode,
        "sl_pct": 0.01,
        "sl_atr_mult": 2.0,
        "rr": 2.5,
        "trail_atr_mult": 2.5,
        "leverage": 2.0,
    }
    rng = np.random.default_rng(3)
    draws = [autotune_search._mutate_exits(rng, elite) for _ in range(200)]
    same_mode = [draw for draw in draws if draw["mode"] == mode]
    assert same_mode
    for field in moving:
        assert len({draw[field] for draw in same_mode}) > 1, field
    for draw in draws:
        assert 0.003 <= draw["sl_pct"] <= 0.03
        assert 1.5 <= draw["rr"] <= 4.0
        assert 1.5 <= draw["trail_atr_mult"] <= 4.0
        assert 1.0 <= draw["sl_atr_mult"] <= 3.5
        assert draw["leverage"] in {1.0, 2.0, 3.0, 5.0}
    assert {draw["leverage"] for draw in draws} != {2.0}


def test_strategy_managed_exits_are_never_mutated() -> None:
    elite = strategy_managed_exit_dict(MANAGED_EXECUTION)
    rng = np.random.default_rng(5)
    assert all(autotune_search._mutate_exits(rng, elite) == elite for _ in range(50))


def test_karpathy_never_repeats_an_effective_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = fixture_ohlcv(n_bars=120, drift=1.0)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))
    _stub_metrics(monkeypatch)

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=SYNTHETIC_LONG,
        n_trials=40,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    register_all_strategies()
    evaluator = TrialEvaluator(
        bars,
        get_strategy(SYNTHETIC_LONG),
        "long",
        resolve_cost_model("hl_base_taker"),
        ExecutionProfile(),
        compute_trial_metrics,
    )
    keys = [
        evaluator.config_key(trial["params"], trial["exit_cfg"])
        for trial in board["all_trials"]
    ]
    assert len(keys) == 40
    assert len(set(keys)) == 40
    assert board["unique_configs"] == 40
    assert board["space_exhausted"] is False
    adaptive = board["all_trials"][24:]
    assert len({(t["params"]["fast"], t["params"]["slow"]) for t in adaptive}) >= 2


def test_discrete_space_stops_early_and_reports_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-point grid with fixed managed exits has exactly one configuration."""
    bars = fixture_ohlcv(n_bars=180, drift=1.0)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: (bars, {}))

    result = autotune.run_autotune(
        data_root=tmp_path,
        strategy_name=_SINGLE_MANAGED,
        n_trials=5,
        train_fraction=1.0,
        no_export=True,
    )

    board = json.loads(result.board_path.read_text())
    assert result.n_trials == 1
    assert result.n_trials_requested == 5
    assert result.space_exhausted is True
    assert board["space_exhausted"] is True
    assert board["n_trials_requested"] == 5
    assert len(board["all_trials"]) == 1
    assert any("exhausted" in warning for warning in result.warnings)


@pytest.mark.parametrize("symbol", ["SOL", "ETH", "kPEPE"])
def test_declared_leverage_is_checked_before_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symbol: str
) -> None:
    monkeypatch.setattr(
        autotune,
        "load_research_history",
        lambda *_a, **_k: pytest.fail("history read before venue leverage check"),
    )
    with pytest.raises(ValueError, match="leverage"):
        autotune.run_autotune(
            data_root=tmp_path,
            strategy_name=_HIGH_LEVERAGE,
            symbol=symbol,
        )
