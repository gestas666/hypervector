"""Measured trial evaluation with explicit technical-failure accounting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging

import pandas as pd

from hypervector.strategies.hypervelocity_contract import HypervelocityContract
from hypervector.strategies.registry import StrategySpec
from hypervector.sweep.autotune_sampling import _hypervelocity_exit_dict
from hypervector.sweep.costs import CostModel
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.sizing import RiskConfig

_TRIAL_ERRORS = (
    ArithmeticError,
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)
_INITIAL_CASH = 10_000.0
logger = logging.getLogger(__name__)


@dataclass
class TrialEvaluator:
    """Evaluate declared trials; report weak outcomes without implicit gates."""

    bars: pd.DataFrame
    strategy: StrategySpec
    direction: str
    cost: CostModel
    hypervelocity: bool
    calculate: Callable[..., dict[str, object]]
    apply_penalties: bool = False
    trials: list[dict[str, object]] = field(default_factory=list)

    def evaluate(
        self, params: dict[str, object], exits: dict[str, object], number: int
    ) -> float:
        """Retain technical errors separately from successful measurements."""
        try:
            metrics, reported = self._measure(params, exits)
            score = self._score(metrics)
        except _TRIAL_ERRORS as exc:
            logger.warning("Autotune trial %d failed: %s", number, exc)
            self.trials.append(
                {
                    "trial_number": number,
                    "status": "error",
                    "error": str(exc),
                    "params": params,
                    "exit_cfg": exits,
                }
            )
            return float("-inf")
        self.trials.append(
            {
                "trial_number": number,
                "status": "ok",
                "params": params,
                "exit_cfg": reported,
                "metrics": metrics,
            }
        )
        return score

    def _measure(
        self, params: dict[str, object], exits: dict[str, object]
    ) -> tuple[dict[str, object], dict[str, object]]:
        entries, exit_signals, _ = self.strategy.build_signals(self.bars, **params)
        contract = HypervelocityContract() if self.hypervelocity else None
        exit_config, leverage = self._exits(exits, contract)
        metrics = self.calculate(
            self.bars["close"].astype(float),
            entries,
            exit_signals,
            direction=self.direction,
            init_cash=_INITIAL_CASH,
            df=self.bars,
            cost=self.cost,
            exit_cfg=exit_config,
            risk_cfg=RiskConfig(max_size_frac=leverage),
            apply_costs=True,
            fixed_notional_fraction=contract.notional_fraction if contract else None,
            fixed_margin_fraction=contract.margin_fraction if contract else None,
            strategy_managed_exits=self.hypervelocity,
        )
        reported = (
            _hypervelocity_exit_dict()
            if contract
            else {**exit_config.to_dict(), "leverage": leverage}
        )
        return metrics, reported

    def _exits(
        self, exits: dict[str, object], contract: HypervelocityContract | None
    ) -> tuple[ExitConfig, float]:
        if contract is not None:
            return ExitConfig(), contract.leverage
        return ExitConfig(
            mode=exits.get("mode", "atr"),
            sl_pct=exits.get("sl_pct", 0.01),
            sl_atr_mult=exits.get("sl_atr_mult", 2.0),
            rr=exits.get("rr", 2.0),
            trail_atr_mult=exits.get("trail_atr_mult", 2.0),
        ), float(exits.get("leverage", 2.0))

    def _score(self, metrics: dict[str, object]) -> float:
        trades = int(metrics.get("trade_count", metrics.get("trades", 0)))
        sharpe = float(metrics.get("sharpe", -99.0))
        net_pnl = float(metrics.get("net_pnl", -9999.0))
        drawdown = float(metrics.get("max_drawdown", 100.0))
        if self.apply_penalties:
            if trades < 10:
                return -50.0 + trades
            if drawdown > 25.0:
                return -20.0 - drawdown
        return sharpe + net_pnl / 1000.0
