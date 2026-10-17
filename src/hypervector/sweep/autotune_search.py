"""Search algorithms over an explicitly supplied measured evaluator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from hypervector.sweep.autotune_evaluation import TrialEvaluator
from hypervector.sweep.autotune_models import SEARCH_SEED, SearchSettings
from hypervector.sweep.autotune_sampling import (
    EXIT_BOUNDS,
    EXIT_LEVERAGE_LEVELS,
    EXIT_MODE_FIELDS,
)
from hypervector.sweep.exits import EXIT_MODES

#: Columns produced by order-book alignment that the book gate consumes.
BOOK_COLUMNS = frozenset({"spread_bps", "obi_5"})
#: Bounded attempts to find an unseen configuration before declaring the
#: (discrete) search space exhausted.
MAX_RESAMPLE_ATTEMPTS = 64
_EXIT_MODE_SWITCH_PROBABILITY = 0.1
_LEVERAGE_STEP_PROBABILITY = 0.2


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


@dataclass(frozen=True)
class SearchStats:
    """What the search itself observed, for the trial board."""

    space_exhausted: bool = False
    duplicate_resamples: int = 0


def run_karpathy(
    settings: SearchSettings, evaluator: TrialEvaluator, tools: SamplingTools
) -> SearchStats:
    """Random coarse phase, then elite zoom, never measuring a config twice.

    Elites rank by the evaluator's objective value, independent of its sign.
    When no unseen configuration is found within ``MAX_RESAMPLE_ATTEMPTS``
    (a fully discrete space), the search stops early and reports exhaustion.
    """
    rng = np.random.default_rng(SEARCH_SEED)
    elites: list[tuple[float, dict[str, object], dict[str, object]]] = []
    coarse_trials = max(5, int(settings.n_trials * 0.6))
    seen: set[object] = set()
    resamples = 0
    for number in range(settings.n_trials):
        candidate = None
        for attempt in range(MAX_RESAMPLE_ATTEMPTS):
            adaptive = number >= coarse_trials and elites
            # Zoom first; fall back to fresh samples if the neighbourhood is spent.
            if adaptive and attempt < MAX_RESAMPLE_ATTEMPTS // 2:
                _, elite_params, elite_exits = elites[int(rng.integers(0, len(elites)))]
                params = tools.mutate(rng, elite_params, evaluator.strategy.param_grid)
                exits = _mutate_exits(rng, elite_exits)
            else:
                params = tools.sample(rng, evaluator.strategy.param_grid)
                exits = tools.random_exits(rng, hypervelocity=evaluator.hypervelocity)
            params = tools.clamp(params, settings.symbol)
            key = evaluator.config_key(params, exits)
            if key not in seen:
                candidate = (key, params, exits)
                break
            resamples += 1
        if candidate is None:
            return SearchStats(space_exhausted=True, duplicate_resamples=resamples)
        key, params, exits = candidate
        seen.add(key)
        score = evaluator.evaluate(params, exits, number)
        if evaluator.trials[-1]["status"] == "ok":
            elites.append((score, params, exits))
            elites.sort(key=lambda item: item[0], reverse=True)
            elites = elites[:5]
    return SearchStats(space_exhausted=False, duplicate_resamples=resamples)


def _scale_within(rng: np.random.Generator, value: float, name: str) -> float:
    low, high, digits = EXIT_BOUNDS[name]
    candidate = float(value) * float(rng.uniform(0.9, 1.1))
    return round(min(max(candidate, low), high), digits)


def _mutate_exits(
    rng: np.random.Generator, elite: dict[str, object]
) -> dict[str, object]:
    """Mutate the exit fields the elite's mode uses; keep fixed lifecycles fixed.

    Strategy-managed exits (e.g. Hypervelocity ``strategy_target_only``) are
    returned unchanged. Occasionally the mode switches or the sizing cap steps
    to a neighbouring level.
    """
    exits = dict(elite)
    mode = exits.get("mode")
    if mode not in EXIT_MODES:
        return exits
    if float(rng.uniform(0.0, 1.0)) < _EXIT_MODE_SWITCH_PROBABILITY:
        others = [item for item in EXIT_MODES if item != mode]
        mode = others[int(rng.integers(0, len(others)))]
        exits["mode"] = mode
    for name in EXIT_MODE_FIELDS[str(mode)]:
        default = (EXIT_BOUNDS[name][0] + EXIT_BOUNDS[name][1]) / 2.0
        exits[name] = _scale_within(rng, float(exits.get(name, default)), name)  # type: ignore[arg-type]
    if float(rng.uniform(0.0, 1.0)) < _LEVERAGE_STEP_PROBABILITY:
        levels = list(EXIT_LEVERAGE_LEVELS)
        current = float(exits.get("leverage", 2.0))  # type: ignore[arg-type]
        position = min(range(len(levels)), key=lambda i: abs(levels[i] - current))
        neighbours = [i for i in (position - 1, position + 1) if 0 <= i < len(levels)]
        exits["leverage"] = levels[neighbours[int(rng.integers(0, len(neighbours)))]]
    return exits


def searches_book_dimensions(evaluator: TrialEvaluator) -> bool:
    """Book dimensions exist only for book-gating builders with aligned book data."""
    return (
        not evaluator.hypervelocity
        and bool(getattr(evaluator.strategy, "supports_book_gate", False))
        and BOOK_COLUMNS.issubset(evaluator.bars.columns)
    )


def optuna_objective(
    settings: SearchSettings,
    evaluator: TrialEvaluator,
    tools: SamplingTools,
    trial: OptunaTrial,
) -> float:
    """Sample the same grid and, where real, the book features for Optuna runs."""
    params = {
        name: trial.suggest_categorical(name, values)
        for name, values in evaluator.strategy.param_grid.items()
        if isinstance(values, list) and values
    }
    if searches_book_dimensions(evaluator):
        params["book_gate"] = trial.suggest_categorical("book_gate", [True, False])
        params["max_spread_bps"] = trial.suggest_float(
            "max_spread_bps", 1.5, 10.0, step=0.5
        )
        params["min_obi"] = trial.suggest_float("min_obi", -0.5, 0.4, step=0.1)
    exits = tools.optuna_exits(trial, hypervelocity=evaluator.hypervelocity)
    return evaluator.evaluate(tools.clamp(params, settings.symbol), exits, trial.number)
