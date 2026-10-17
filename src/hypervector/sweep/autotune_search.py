"""Search algorithms over an explicitly supplied measured evaluator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from hypervector.sweep.autotune_evaluation import TrialEvaluator
from hypervector.sweep.autotune_models import SearchSettings


class OptunaTrial(Protocol):
    """Only the sampler interface consumed by this search."""

    number: int

    def suggest_categorical(self, name: str, choices: list[object]) -> object: ...
    def suggest_float(
        self, name: str, low: float, high: float, *, step: float
    ) -> float: ...


@dataclass(frozen=True)
class SamplingTools:
    """Explicit compatibility hooks for strategy parameter sampling."""

    sample: Callable[..., dict[str, object]]
    mutate: Callable[..., dict[str, object]]
    random_exits: Callable[..., dict[str, object]]
    optuna_exits: Callable[..., dict[str, object]]
    clamp: Callable[..., dict[str, object]]


def run_karpathy(
    settings: SearchSettings, evaluator: TrialEvaluator, tools: SamplingTools
) -> None:
    """Use successful measured trials as elites, independent of score sign."""
    rng = np.random.default_rng(42)
    elites: list[tuple[float, dict[str, object], dict[str, object]]] = []
    coarse_trials = max(5, int(settings.n_trials * 0.6))
    for number in range(settings.n_trials):
        if number >= coarse_trials and elites:
            _, elite_params, elite_exits = elites[int(rng.integers(0, len(elites)))]
            params = tools.mutate(rng, elite_params, evaluator.strategy.param_grid)
            exits = _mutate_exits(rng, elite_exits)
        else:
            params = tools.sample(rng, evaluator.strategy.param_grid)
            exits = tools.random_exits(rng, hypervelocity=evaluator.hypervelocity)
        params = tools.clamp(params, settings.symbol)
        score = evaluator.evaluate(params, exits, number)
        if evaluator.trials[-1]["status"] == "ok":
            elites.append((score, params, exits))
            elites.sort(key=lambda item: item[0], reverse=True)
            elites = elites[:5]


def _mutate_exits(
    rng: np.random.Generator, elite: dict[str, object]
) -> dict[str, object]:
    exits = dict(elite)
    if "sl_atr_mult" in exits:
        candidate = float(exits["sl_atr_mult"]) * float(rng.uniform(0.9, 1.1))
        exits["sl_atr_mult"] = round(min(max(candidate, 1.0), 3.5), 2)
    return exits


def optuna_objective(
    settings: SearchSettings,
    evaluator: TrialEvaluator,
    tools: SamplingTools,
    trial: OptunaTrial,
) -> float:
    """Sample the same grid and optional book features for explicit Optuna runs."""
    params = {
        name: trial.suggest_categorical(name, values)
        for name, values in evaluator.strategy.param_grid.items()
        if isinstance(values, list) and values
    }
    if not evaluator.hypervelocity and (
        {"spread_bps", "obi_5"} & set(evaluator.bars.columns)
        or settings.book_data_path is not None
    ):
        params["book_gate"] = trial.suggest_categorical("book_gate", [True, False])
        params["max_spread_bps"] = trial.suggest_float(
            "max_spread_bps", 1.5, 10.0, step=0.5
        )
        params["min_obi"] = trial.suggest_float("min_obi", -0.5, 0.4, step=0.1)
    exits = tools.optuna_exits(trial, hypervelocity=evaluator.hypervelocity)
    return evaluator.evaluate(tools.clamp(params, settings.symbol), exits, trial.number)
