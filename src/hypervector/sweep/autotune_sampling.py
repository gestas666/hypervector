"""Parameter sampling for Karpathy and optional Optuna search backends.

Any annotations at this compatibility boundary represent plugin-defined
strategy/metric JSON fields rather than an unvalidated execution interface.
"""

from __future__ import annotations
from typing import Any
from hypervector.strategies.hypervelocity_contract import HypervelocityContract

_EXIT_SL_ATR_MIN = 1.0
_EXIT_SL_ATR_MAX = 3.5
_VENUE_LEVERAGE_CAPS = {"BTC": 40.0, "ETH": 25.0, "SOL": 20.0}
_DEFAULT_ALT_LEVERAGE_CAP = 10.0


def _sample_grid_params(rng: Any, param_grid: dict[str, list[Any]]) -> dict[str, Any]:
    """Sample values by index so Python grid types survive NumPy RNG use."""
    return {
        name: values[int(rng.integers(0, len(values)))]
        for name, values in param_grid.items()
        if values
    }


def _mutate_grid_params(
    rng: Any,
    params: dict[str, Any],
    param_grid: dict[str, list[Any]],
) -> dict[str, Any]:
    """Mutate float parameters without leaving their declared search bounds."""
    mutated = dict(params)
    for name, value in params.items():
        numeric_grid = [
            float(item)
            for item in param_grid.get(name, [])
            if type(item) in (int, float)
        ]
        if type(value) is not float or not numeric_grid:
            continue
        candidate = float(value) * float(rng.uniform(0.9, 1.1))
        mutated[name] = round(
            min(max(candidate, min(numeric_grid)), max(numeric_grid)), 4
        )
    return mutated


def _clamp_strategy_leverage(params: dict[str, Any], symbol: str) -> dict[str, Any]:
    """Clamp strategy leverage to the configured Hyperliquid venue cap."""
    if "leverage" not in params:
        return params
    cap = _VENUE_LEVERAGE_CAPS.get(symbol.upper(), _DEFAULT_ALT_LEVERAGE_CAP)
    clamped = dict(params)
    clamped["leverage"] = min(float(params["leverage"]), cap)
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
        "rr": trial.suggest_float("rr", 1.2, 5.0, step=0.3),
        "trail_atr_mult": trial.suggest_float("trail_atr_mult", 1.2, 5.0, step=0.3),
        "leverage": trial.suggest_categorical("leverage", [1.0, 2.0, 3.0, 5.0]),
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
        "leverage": _sample_grid_params(rng, {"leverage": [1.0, 2.0, 3.0, 5.0]})[
            "leverage"
        ],
    }
