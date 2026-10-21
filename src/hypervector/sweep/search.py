"""Grid search with ranking; technical failure only aborts a trial (SRS_HV1_NO_GATES)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from hypervector.strategies.indicators import indicator_cache
from hypervector.strategies.registry import StrategySpec, normalize_direction
from hypervector.sweep.costs import DEFAULT_COST_MODEL, CostModel, resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import RiskConfig

# Grid keys that configure exits rather than the strategy's signal builder.
_EXIT_PARAM_KEYS = frozenset(
    {
        "exit_mode",
        "tp_sl_mode",
        "sl_pct",
        "rr",
        "atr_length",
        "sl_atr_mult",
        "trail_atr_mult",
    }
)


@dataclass
class TrialResult:
    strategy: str
    role: str
    params: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    @property
    def net_pnl(self) -> float:
        return float(self.metrics.get("net_pnl", float("-inf")))

    @property
    def total_return_pct(self) -> float:
        return float(self.metrics.get("total_return_pct", float("-inf")))


def _param_product(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def _trial_exit(params: dict[str, Any], exit_cfg: ExitConfig) -> ExitConfig:
    """Per-trial exit mode override from the grid."""
    if "exit_mode" not in params and "tp_sl_mode" not in params:
        return exit_cfg
    mode = params.get("exit_mode") or params.get("tp_sl_mode")
    return ExitConfig(
        mode=mode,  # type: ignore[arg-type]
        sl_pct=params.get("sl_pct", exit_cfg.sl_pct),
        rr=params.get("rr", exit_cfg.rr),
        atr_length=params.get("atr_length", exit_cfg.atr_length),
        sl_atr_mult=params.get("sl_atr_mult", exit_cfg.sl_atr_mult),
        trail_atr_mult=params.get("trail_atr_mult", exit_cfg.trail_atr_mult),
    )


def run_grid_search(
    df: pd.DataFrame,
    strategy: StrategySpec,
    *,
    param_grid: dict[str, list[Any]] | None = None,
    rank_by: tuple[str, str] = ("net_pnl", "total_return_pct"),
    init_cash: float = 10_000.0,
    cost: CostModel | None = None,
    exit_cfg: ExitConfig | None = None,
    risk_cfg: RiskConfig | None = None,
    conviction: float | pd.Series | None = None,
    apply_costs: bool = True,
    symbol: str | None = None,
    venue_max_leverage: float | None = None,
) -> list[TrialResult]:
    """Run all grid combos; rank ok trials by primary metrics; keep errors last.

    Indicators shared by several trials (identical inputs and parameters) are
    computed once per search via a scoped indicator cache; results are
    identical to per-trial evaluation. ``symbol`` / ``venue_max_leverage``
    select the venue leverage cap and maintenance margin for every trial.
    The strategy's declared :class:`ExecutionProfile` selects fixed sizing and
    strategy-managed exits for every trial.
    """
    cost = cost or resolve_cost_model(DEFAULT_COST_MODEL)
    exit_cfg = exit_cfg or ExitConfig(mode="atr")
    risk_cfg = risk_cfg or RiskConfig()
    grid = param_grid if param_grid is not None else strategy.param_grid
    combos = _param_product(grid)
    results: list[TrialResult] = []
    close = df["close"]
    execution = strategy.execution

    with indicator_cache():
        for params in combos:
            if (
                "fast" in params
                and "slow" in params
                and params["fast"] >= params["slow"]
            ):
                results.append(
                    TrialResult(
                        strategy=strategy.name,
                        role=strategy.role,
                        params=params,
                        status="error",
                        error="fast >= slow",
                    )
                )
                continue
            trial_exit = _trial_exit(params, exit_cfg)
            try:
                build_kwargs = {
                    k: v for k, v in params.items() if k not in _EXIT_PARAM_KEYS
                }
                entries, exits, tag = strategy.build_signals(df, **build_kwargs)
                # Builders may return a descriptive tag (e.g. breakout_long).
                direction = normalize_direction(tag)
                # Optional per-bar conviction from strategy params
                conv = params.get("conviction", conviction)
                metrics = compute_trial_metrics(
                    close,
                    entries,
                    exits,
                    direction=direction,
                    init_cash=init_cash,
                    df=df,
                    cost=cost,
                    exit_cfg=trial_exit,
                    risk_cfg=risk_cfg,
                    conviction=conv,
                    apply_costs=apply_costs,
                    fixed_notional_fraction=execution.fixed_notional_fraction,
                    fixed_margin_fraction=execution.fixed_margin_fraction,
                    strategy_managed_exits=execution.strategy_managed_exits,
                    symbol=symbol,
                    venue_max_leverage=venue_max_leverage,
                )
                results.append(
                    TrialResult(
                        strategy=strategy.name,
                        role=strategy.role,
                        params={**params, "exit_mode": trial_exit.mode},
                        metrics=metrics,
                        status="ok",
                    )
                )
            except Exception as exc:
                results.append(
                    TrialResult(
                        strategy=strategy.name,
                        role=strategy.role,
                        params=params,
                        status="error",
                        error=str(exc),
                    )
                )

    primary, secondary = rank_by

    def sort_key(t: TrialResult) -> tuple:
        ok = 1 if t.status == "ok" else 0
        p = t.metrics.get(primary, float("-inf")) if t.status == "ok" else float("-inf")
        s = (
            t.metrics.get(secondary, float("-inf"))
            if t.status == "ok"
            else float("-inf")
        )
        return (ok, p, s)

    results.sort(key=sort_key, reverse=True)
    return results
