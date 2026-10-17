"""Parameter sampling for Karpathy and optional Optuna search backends.

Any annotations at this compatibility boundary represent plugin-defined
strategy/metric JSON fields rather than an unvalidated execution interface.
"""

from __future__ import annotations
from typing import Any
from hypervector.strategies.hypervelocity_contract import HypervelocityContract
from hypervector.sweep.exits import EXIT_MODES, ExitConfig

# The single research venue-cap table (SRS_HV1_VENUE_SPEC) lives in sizing;
# re-exported here for callers of the historical sampling name.
from hypervector.sweep.sizing import venue_leverage_cap as venue_leverage_cap

_EXIT_SL_ATR_MIN = 1.0
_EXIT_SL_ATR_MAX = 3.5
#: Sizing caps (equity fraction) sampled for generic exits.
EXIT_LEVERAGE_LEVELS: tuple[float, ...] = (1.0, 2.0, 3.0, 5.0)
#: Karpathy exit bounds: (low, high, rounding digits); mutation stays inside.
EXIT_BOUNDS: dict[str, tuple[float, float, int]] = {
    "sl_pct": (0.003, 0.03, 4),
    "sl_atr_mult": (_EXIT_SL_ATR_MIN, _EXIT_SL_ATR_MAX, 2),
    "rr": (1.5, 4.0, 2),
    "trail_atr_mult": (1.5, 4.0, 2),
}
#: Fields each generic exit mode actually consumes (sweep/exits.py).
EXIT_MODE_FIELDS: dict[str, tuple[str, ...]] = {
    "fixed_rr": ("sl_pct", "rr"),
    "atr": ("sl_atr_mult", "rr"),
    "trail": ("trail_atr_mult",),
}
#: Fields that change a measured result, including the ATR warmup fill.
_EFFECTIVE_EXIT_FIELDS: dict[str, tuple[str, ...]] = {
    "fixed_rr": ("sl_pct", "rr"),
    "atr": ("sl_pct", "sl_atr_mult", "rr", "atr_length"),
    "trail": ("sl_pct", "trail_atr_mult", "atr_length"),
}
_INT_STEP_PROBABILITY = 0.5
_CATEGORICAL_SWITCH_PROBABILITY = 0.3


def _sample_grid_params(rng: Any, param_grid: dict[str, list[Any]]) -> dict[str, Any]:
    """Sample values by index so Python grid types survive NumPy RNG use."""
    return {
        name: values[int(rng.integers(0, len(values)))]
        for name, values in param_grid.items()
        if values
    }


def _step_int(rng: Any, value: int, grid: list[Any]) -> int:
    levels = sorted({item for item in grid if type(item) is int})
    if value not in levels or len(levels) < 2:
        return value
    position = levels.index(value)
    neighbours = [
        index for index in (position - 1, position + 1) if 0 <= index < len(levels)
    ]
    return levels[neighbours[int(rng.integers(0, len(neighbours)))]]


def _switch_categorical(rng: Any, value: Any, grid: list[Any]) -> Any:
    others = [
        item for item in grid if not (type(item) is type(value) and item == value)
    ]
    if not others:
        return value
    return others[int(rng.integers(0, len(others)))]


def _mutate_grid_params(
    rng: Any,
    params: dict[str, Any],
    param_grid: dict[str, list[Any]],
) -> dict[str, Any]:
    """Move every parameter kind locally without leaving its declared grid.

    Floats are scaled by U(0.9, 1.1) and clamped to the grid bounds; ints step
    to a neighbouring grid value; bools and other categories switch to another
    grid value. Discrete moves are probabilistic so an elite's values can be
    kept while other dimensions are refined. Only ``rng.integers`` and
    ``rng.uniform`` are used.
    """
    mutated = dict(params)
    for name, value in params.items():
        grid = list(param_grid.get(name, []))
        if not grid:
            continue
        if type(value) is float:
            numeric_grid = [float(item) for item in grid if type(item) in (int, float)]
            if not numeric_grid:
                continue
            candidate = float(value) * float(rng.uniform(0.9, 1.1))
            mutated[name] = round(
                min(max(candidate, min(numeric_grid)), max(numeric_grid)), 4
            )
        elif type(value) is int:
            if float(rng.uniform(0.0, 1.0)) < _INT_STEP_PROBABILITY:
                mutated[name] = _step_int(rng, value, grid)
        elif float(rng.uniform(0.0, 1.0)) < _CATEGORICAL_SWITCH_PROBABILITY:
            mutated[name] = _switch_categorical(rng, value, grid)
    return mutated


def _clamp_strategy_leverage(params: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Clamp strategy leverage to the configured Hyperliquid venue cap."""
    if "leverage" not in params:
        return params
    clamped = dict(params)
    clamped["leverage"] = min(float(params["leverage"]), venue_leverage_cap(symbol))
    return clamped


def _hypervelocity_exit_dict() -> dict[str, Any]:
    """Return the fixed strategy-managed exit contract for trial reporting."""
    contract = HypervelocityContract()
    return {
        "mode": "strategy_target_only",
        "target_margin_pct": contract.target_margin_pct,
        "target_price_fraction": contract.target_price_fraction,
        "stop": None,
        "leverage": contract.leverage,
        "range_policy": contract.open_position_range_policy,
    }


def _optuna_exit_dict(trial: Any, *, hypervelocity: bool) -> dict[str, Any]:
    """Sample generic exits or return the immutable Hypervelocity lifecycle."""
    if hypervelocity:
        return _hypervelocity_exit_dict()
    return {
        "mode": trial.suggest_categorical("exit_mode", ["atr", "trail", "fixed_rr"]),
        "sl_pct": trial.suggest_float("sl_pct", 0.003, 0.03, step=0.003),
        "sl_atr_mult": trial.suggest_float("sl_atr_mult", 0.8, 4.0, step=0.4),
        "rr": trial.suggest_float("rr", 1.2, 4.8, step=0.3),
        "trail_atr_mult": trial.suggest_float("trail_atr_mult", 1.2, 4.8, step=0.3),
        "leverage": trial.suggest_categorical("leverage", list(EXIT_LEVERAGE_LEVELS)),
    }


def _random_exit_dict(rng: Any, *, hypervelocity: bool) -> dict[str, Any]:
    """Sample generic exits or return the immutable Hypervelocity lifecycle."""
    if hypervelocity:
        return _hypervelocity_exit_dict()
    return {
        "mode": _sample_grid_params(rng, {"mode": ["atr", "trail", "fixed_rr"]})[
            "mode"
        ],
        "sl_pct": round(float(rng.uniform(0.003, 0.03)), 4),
        "sl_atr_mult": round(float(rng.uniform(_EXIT_SL_ATR_MIN, _EXIT_SL_ATR_MAX)), 1),
        "rr": round(float(rng.uniform(1.5, 4.0)), 1),
        "trail_atr_mult": round(float(rng.uniform(1.5, 4.0)), 1),
        "leverage": _sample_grid_params(
            rng, {"leverage": list(EXIT_LEVERAGE_LEVELS)}
        )["leverage"],
    }


def exit_space(*, hypervelocity: bool, sampler: str) -> dict[str, Any]:
    """Describe the exit dimensions a sampler searches, for board provenance."""
    if hypervelocity:
        return {"fixed": _hypervelocity_exit_dict()}
    if sampler == "karpathy":
        return {
            "mode": ["atr", "trail", "fixed_rr"],
            **{name: [low, high] for name, (low, high, _) in EXIT_BOUNDS.items()},
            "leverage": list(EXIT_LEVERAGE_LEVELS),
        }
    return {
        "mode": ["atr", "trail", "fixed_rr"],
        "sl_pct": {"low": 0.003, "high": 0.03, "step": 0.003},
        "sl_atr_mult": {"low": 0.8, "high": 4.0, "step": 0.4},
        "rr": {"low": 1.2, "high": 4.8, "step": 0.3},
        "trail_atr_mult": {"low": 1.2, "high": 4.8, "step": 0.3},
        "leverage": list(EXIT_LEVERAGE_LEVELS),
    }


def effective_exit_key(exits: dict[str, Any]) -> tuple[Any, ...]:
    """Key the exit settings that change a measurement, resolved like a trial.

    Defaults mirror ``TrialEvaluator`` so an input exit dict and its reported
    ``ExitConfig`` form produce the same key. Unknown modes keep every field.
    """
    mode = exits.get("mode", "atr")
    if mode not in EXIT_MODES:
        return ("raw", tuple(sorted((str(k), repr(v)) for k, v in exits.items())))
    defaults = {
        "sl_pct": 0.01,
        "sl_atr_mult": 2.0,
        "rr": 2.0,
        "trail_atr_mult": 2.0,
        "atr_length": ExitConfig.atr_length,
    }
    values = tuple(
        (name, float(exits.get(name, defaults[name])))
        for name in _EFFECTIVE_EXIT_FIELDS[mode]
    )
    return (mode, values, float(exits.get("leverage", 2.0)))
