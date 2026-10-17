"""Measured trial evaluation with explicit technical-failure accounting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import math

import pandas as pd

from hypervector.strategies.hypervelocity_contract import HypervelocityContract
from hypervector.strategies.registry import StrategySpec
from hypervector.sweep.autotune_models import DEFAULT_OBJECTIVE, OBJECTIVES
from hypervector.sweep.autotune_sampling import (
    _hypervelocity_exit_dict,
    effective_exit_key,
)
from hypervector.sweep.costs import CostModel
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.sizing import RiskConfig

_INITIAL_CASH = 10_000.0
_STRATEGY_TARGET_ONLY = "strategy_target_only"
logger = logging.getLogger(__name__)


def sharpe_defined(metrics: dict[str, object]) -> bool:
    """A Sharpe ratio is only defined for a trial that traded.

    ``compute_trial_metrics`` reports an undefined Sharpe as ``0.0``; the
    autotune layer labels it rather than changing the shared metric bytes.
    """
    try:
        return int(metrics.get("trade_count", metrics.get("trades", 0)) or 0) > 0
    except (TypeError, ValueError):
        return False


def _number(value: object, default: float) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number


def objective_value(metrics: dict[str, object], objective: str) -> float:
    """Return the one scalar that the search, the elites and the export rank by.

    ``net_pnl`` (default) follows the primary rank; ``score`` is the historical
    search score ``sharpe + net_pnl / 1000``; ``sharpe`` ranks trials whose
    Sharpe is undefined (no trades) below every defined Sharpe. Non-finite
    values rank last. This is a ranking, never a gate.
    """
    if objective not in OBJECTIVES:
        raise ValueError(
            f"unsupported autotune objective {objective!r}; choose one of {', '.join(OBJECTIVES)}"
        )
    net_pnl = _number(metrics.get("net_pnl", -9999.0), -9999.0)
    sharpe = _number(metrics.get("sharpe", -99.0), -99.0)
    if objective == "net_pnl":
        value = net_pnl
    elif objective == "score":
        value = sharpe + net_pnl / 1000.0
    else:
        value = sharpe if sharpe_defined(metrics) else float("-inf")
    return value if math.isfinite(value) else float("-inf")


def selection_key(
    trial: dict[str, object], objective: str
) -> tuple[float, float, int]:
    """Order successful trials: objective, then total return, then earliest."""
    metrics = trial["metrics"]
    assert isinstance(metrics, dict)
    total_return = _number(metrics.get("total_return_pct", float("-inf")), float("-inf"))
    if not math.isfinite(total_return):
        total_return = float("-inf")
    return (
        objective_value(metrics, objective),
        total_return,
        -int(trial["trial_number"]),  # type: ignore[call-overload]
    )


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float):
        return float(value)
    return (type(value).__name__, repr(value))


@dataclass
class TrialEvaluator:
    """Evaluate declared trials; report weak outcomes without implicit gates.

    Every ``Exception`` raised while measuring one trial is a technical failure
    of that trial only: it is recorded with its type and the search continues.
    ``BaseException`` (e.g. ``KeyboardInterrupt``) is never swallowed.
    """

    bars: pd.DataFrame
    strategy: StrategySpec
    direction: str
    cost: CostModel
    hypervelocity: bool
    calculate: Callable[..., dict[str, object]]
    objective: str = DEFAULT_OBJECTIVE
    trials: list[dict[str, object]] = field(default_factory=list)
    _measured: dict[object, dict[str, object]] = field(
        default_factory=dict, repr=False
    )

    def config_key(
        self, params: dict[str, object], exits: dict[str, object]
    ) -> tuple[object, ...]:
        """Identify the effective configuration a trial would measure."""
        exit_key: tuple[object, ...] = (
            (_STRATEGY_TARGET_ONLY,) if self.hypervelocity else effective_exit_key(exits)
        )
        return (_freeze(params), exit_key)

    def evaluate(
        self, params: dict[str, object], exits: dict[str, object], number: int
    ) -> float:
        """Record one trial and return its objective value (``-inf`` on failure).

        A configuration already measured is not re-run: the trial is recorded
        with the earlier measurement and ``duplicate_of``.
        """
        key = self.config_key(params, exits)
        earlier = self._measured.get(key)
        if earlier is not None:
            record = {
                **earlier,
                "trial_number": number,
                "params": params,
                "duplicate_of": earlier["trial_number"],
            }
            if record["status"] == "error":
                record["exit_cfg"] = exits
            self.trials.append(record)
            return self._recorded_value(record)
        try:
            metrics, reported = self.measure(params, exits)
            value = objective_value(metrics, self.objective)
        except Exception as exc:  # noqa: BLE001 - per-trial technical failure
            logger.warning(
                "Autotune trial %d failed: %s: %s", number, type(exc).__name__, exc
            )
            record = {
                "trial_number": number,
                "status": "error",
                "error_type": type(exc).__name__,
                "error": f"{type(exc).__name__}: {exc}",
                "params": params,
                "exit_cfg": exits,
            }
            self.trials.append(record)
            self._measured[key] = record
            return float("-inf")
        record = {
            "trial_number": number,
            "status": "ok",
            "params": params,
            "exit_cfg": reported,
            "metrics": metrics,
            "objective_value": value if math.isfinite(value) else None,
            "sharpe_defined": sharpe_defined(metrics),
        }
        self.trials.append(record)
        self._measured[key] = record
        return value

    def _recorded_value(self, record: dict[str, object]) -> float:
        if record["status"] != "ok":
            return float("-inf")
        metrics = record["metrics"]
        assert isinstance(metrics, dict)
        return objective_value(metrics, self.objective)

    def measure(
        self,
        params: dict[str, object],
        exits: dict[str, object],
        *,
        evaluation_start: int = 0,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Measure one configuration on ``bars[evaluation_start:]``.

        Signals are always built on every bar (earlier bars act as causal
        warmup); only the evaluation window is scored.
        """
        entries, exit_signals, _ = self.strategy.build_signals(self.bars, **params)
        window = self.bars.iloc[evaluation_start:]
        if evaluation_start:
            entries = entries.iloc[evaluation_start:]
            exit_signals = exit_signals.iloc[evaluation_start:]
        contract = HypervelocityContract() if self.hypervelocity else None
        exit_config, leverage = self._exits(exits, contract)
        metrics = self.calculate(
            window["close"].astype(float),
            entries,
            exit_signals,
            direction=self.direction,
            init_cash=_INITIAL_CASH,
            df=window,
            cost=self.cost,
            exit_cfg=exit_config,
            risk_cfg=RiskConfig(max_size_frac=leverage),
            apply_costs=True,
            fixed_notional_fraction=contract.notional_fraction if contract else None,
            fixed_margin_fraction=contract.margin_fraction if contract else None,
            strategy_managed_exits=self.hypervelocity,
        )
        if contract is not None:
            # The run used strategy-managed exits with no stop; report that
            # instead of the placeholder ExitConfig mode.
            metrics = {**metrics, "exit_mode": _STRATEGY_TARGET_ONLY}
            reported = _hypervelocity_exit_dict()
        else:
            reported = {**exit_config.to_dict(), "leverage": leverage}
        return metrics, reported

    def _exits(
        self, exits: dict[str, object], contract: HypervelocityContract | None
    ) -> tuple[ExitConfig, float]:
        if contract is not None:
            return ExitConfig(), contract.leverage
        return ExitConfig(
            mode=exits.get("mode", "atr"),  # type: ignore[arg-type]
            sl_pct=exits.get("sl_pct", 0.01),  # type: ignore[arg-type]
            sl_atr_mult=exits.get("sl_atr_mult", 2.0),  # type: ignore[arg-type]
            rr=exits.get("rr", 2.0),  # type: ignore[arg-type]
            trail_atr_mult=exits.get("trail_atr_mult", 2.0),  # type: ignore[arg-type]
        ), float(exits.get("leverage", 2.0))  # type: ignore[arg-type]
