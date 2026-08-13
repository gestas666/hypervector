"""Karpathy / Optuna Dual Autotuning Strategy Optimization Engine.

Combines Karpathy-style continuous stochastic mutation + Optuna TPE sampling
across strategy parameters, leverage levels, TP/SL multipliers, and fee models.
Fully ungated per project charter (SRS_HV1_NO_GATES).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from hypervector.data.pipeline import load_research_history
from hypervector.strategies import register_all_strategies
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import RiskConfig

logger = logging.getLogger(__name__)

_EXIT_SL_ATR_MIN = 1.0
_EXIT_SL_ATR_MAX = 3.5
_VENUE_LEVERAGE_CAPS = {"BTC": 40.0, "ETH": 25.0, "SOL": 20.0}
_DEFAULT_ALT_LEVERAGE_CAP = 10.0

try:
    import optuna  # type: ignore[import-untyped]

    HAVE_OPTUNA = True
except ImportError:
    HAVE_OPTUNA = False


@dataclass
class AutotuneResult:
    strategy_name: str
    symbol: str
    timeframe: str
    lookback_days: int
    n_trials: int
    sampler_used: str
    best_params: dict[str, Any]
    best_exit_cfg: dict[str, Any]
    best_metrics: dict[str, Any]
    export_dir: Path | None
    board_path: Path


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


def _export_autotune_candidate(
    *,
    root: Path,
    stamp: str,
    strategy_name: str,
    role: str,
    symbol: str,
    timeframe: str,
    lookback_days: int,
    fee_model: str,
    provenance: dict[str, Any],
    best_params: dict[str, Any],
    best_exit_dict: dict[str, Any],
    best_metrics: dict[str, Any],
) -> Path:
    """Write a strict Phase-2 bundle through the canonical exporter."""
    from hypervector.export.phase2 import export_candidate

    if is_hypervelocity_strategy(strategy_name):
        contract = HypervelocityContract()
        exit_cfg = ExitConfig(
            mode="fixed_rr",
            sl_pct=contract.target_price_fraction,
            rr=1.0,
        )
        risk_cfg = RiskConfig(
            risk_pct_min=contract.margin_fraction,
            risk_pct_max=contract.margin_fraction,
            max_size_frac=contract.notional_fraction,
        )
    else:
        exit_cfg = ExitConfig(
            **{k: v for k, v in best_exit_dict.items() if k != "leverage"}
        )
        risk_cfg = RiskConfig(max_size_frac=float(best_exit_dict.get("leverage", 1.0)))
    candidate_id = f"exp_{strategy_name}_{timeframe}_{stamp}"
    return export_candidate(
        root / "exports",
        run_id=stamp,
        meta={
            "track": role,
            "symbol": symbol,
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "init_cash": 10_000.0,
            "tp_sl_mode": exit_cfg.mode,
            "exits": exit_cfg.to_dict(),
            "risk": risk_cfg.to_dict(),
            "costs": resolve_cost_model(fee_model).to_dict(),
            "apply_costs": True,
            "data_provenance": provenance,
            "fee_model": fee_model,
            "hypervelocity_contract": (
                _hypervelocity_exit_dict()
                if is_hypervelocity_strategy(strategy_name)
                else None
            ),
        },
        params={
            "strategy": strategy_name,
            "role": role,
            "exit_mode": exit_cfg.mode,
            **best_params,
        },
        metrics=best_metrics,
        candidate_id=candidate_id,
        strict=True,
    )


def run_autotune(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
    symbol: str = "BTC",
    timeframe: str = "5m",
    lookback_days: int = 180,
    strategy_name: str = "crown_stack_long",
    n_trials: int = 100,
    fee_model: str = "hl_taker_default",
    book_data_path: str | Path | None = None,
    sampler: str = "hybrid",
    no_export: bool = False,
    export_best: bool = True,
    apply_penalties: bool = False,
) -> AutotuneResult:
    """Run parameter autotuning using Karpathy random-adaptive mutation or Optuna TPE."""
    root = Path(root or data_root or Path.cwd())
    no_export = no_export or (not export_best)
    register_all_strategies()

    # Load market history
    df, provenance = load_research_history(
        root,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
    )
    if df.empty:
        raise RuntimeError(f"No research history found for {symbol} {timeframe}")

    # Align orderbook if provided
    if book_data_path and Path(book_data_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

        df_book = load_l2_jsonl(book_data_path)
        df = align_orderbook_to_ohlcv(df, df_book)

    close = df["close"].astype(float)
    direction = "short" if "short" in strategy_name.lower() else "long"
    hypervelocity = is_hypervelocity_strategy(strategy_name)
    effective_fee_model = "hl_maker" if hypervelocity else fee_model
    cost = resolve_cost_model(effective_fee_model)
    spec = get_strategy(strategy_name)

    trials_log: list[dict[str, Any]] = []

    def evaluate_config(
        params: dict[str, Any], exit_dict: dict[str, Any], trial_num: int
    ) -> float:
        try:
            entries, exits, _ = spec.build_signals(df, **params)
            if hypervelocity:
                contract = HypervelocityContract()
                exit_cfg = ExitConfig()
                leverage = contract.leverage
                reported_exit = _hypervelocity_exit_dict()
            else:
                contract = None
                exit_cfg = ExitConfig(
                    mode=exit_dict.get("mode", "atr"),
                    sl_pct=exit_dict.get("sl_pct", 0.01),
                    sl_atr_mult=exit_dict.get("sl_atr_mult", 2.0),
                    rr=exit_dict.get("rr", 2.0),
                    trail_atr_mult=exit_dict.get("trail_atr_mult", 2.0),
                )
                leverage = float(exit_dict.get("leverage", 2.0))
                reported_exit = {**exit_cfg.to_dict(), "leverage": leverage}
            risk_cfg = RiskConfig(max_size_frac=leverage)

            m = compute_trial_metrics(
                close,
                entries,
                exits,
                direction=direction,
                init_cash=10_000.0,
                df=df,
                cost=cost,
                exit_cfg=exit_cfg,
                risk_cfg=risk_cfg,
                apply_costs=True,
                fixed_notional_fraction=(
                    contract.notional_fraction if contract is not None else None
                ),
                fixed_margin_fraction=(
                    contract.margin_fraction if contract is not None else None
                ),
                strategy_managed_exits=hypervelocity,
            )

            trades = int(m.get("trade_count", m.get("trades", 0)))
            sharpe = float(m.get("sharpe", -99.0))
            net_pnl = float(m.get("net_pnl", -9999.0))
            max_dd = float(m.get("max_drawdown", 100.0))

            trials_log.append(
                {
                    "trial_number": trial_num,
                    "status": "ok",
                    "params": params,
                    "exit_cfg": reported_exit,
                    "metrics": m,
                }
            )

            # Optional penalties (disabled by default for ungated charter research)
            if apply_penalties:
                if trades < 10:
                    return -50.0 + trades
                if max_dd > 25.0:
                    return -20.0 - max_dd

            # Primary objective score (sharpe + normalized net PnL)
            return sharpe + (net_pnl / 1000.0)

        except Exception as exc:
            logger.warning("Autotune trial %d failed: %s", trial_num, exc)
            trials_log.append(
                {
                    "trial_number": trial_num,
                    "status": "error",
                    "error": str(exc),
                    "params": params,
                    "exit_cfg": exit_dict,
                }
            )
            return -999.0

    # Determine execution path based on sampler argument
    use_optuna = HAVE_OPTUNA and sampler in ("optuna", "hybrid")

    if use_optuna:

        def objective(trial: optuna.Trial) -> float:
            params: dict[str, Any] = {}
            # Generic parameter sampling from StrategySpec.param_grid
            if hasattr(spec, "param_grid") and spec.param_grid:
                for p_name, p_vals in spec.param_grid.items():
                    if isinstance(p_vals, list) and p_vals:
                        params[p_name] = trial.suggest_categorical(p_name, p_vals)

            if not hypervelocity and (
                "spread_bps" in df.columns
                or "obi_5" in df.columns
                or book_data_path is not None
            ):
                params["book_gate"] = trial.suggest_categorical(
                    "book_gate", [True, False]
                )
                params["max_spread_bps"] = trial.suggest_float(
                    "max_spread_bps", 1.5, 10.0, step=0.5
                )
                params["min_obi"] = trial.suggest_float("min_obi", -0.5, 0.4, step=0.1)

            exit_dict = _optuna_exit_dict(trial, hypervelocity=hypervelocity)
            params = _clamp_strategy_leverage(params, symbol)
            return evaluate_config(params, exit_dict, trial.number)

        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=42)
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    else:
        # Karpathy-style Random-Adaptive Autotune Engine
        rng = np.random.default_rng(42)
        best_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

        coarse_trials = max(5, int(n_trials * 0.6))

        for t in range(n_trials):
            if t >= coarse_trials and best_candidates:
                elite_index = int(rng.integers(0, len(best_candidates)))
                _, elite_params, elite_exit = best_candidates[elite_index]
                params = _mutate_grid_params(rng, elite_params, spec.param_grid)
                exit_dict = dict(elite_exit)

                if "sl_atr_mult" in exit_dict:
                    candidate = float(exit_dict["sl_atr_mult"]) * float(
                        rng.uniform(0.9, 1.1)
                    )
                    exit_dict["sl_atr_mult"] = round(
                        min(max(candidate, _EXIT_SL_ATR_MIN), _EXIT_SL_ATR_MAX),
                        2,
                    )
            else:
                params = _sample_grid_params(rng, spec.param_grid)

                exit_dict = _random_exit_dict(rng, hypervelocity=hypervelocity)

            params = _clamp_strategy_leverage(params, symbol)
            score = evaluate_config(params, exit_dict, t)
            if score > -50.0:
                best_candidates.append((score, params, exit_dict))
                best_candidates.sort(key=lambda x: x[0], reverse=True)
                best_candidates = best_candidates[:5]

    # Process best trial results sorted by net PnL / return (primary charter ranking)
    valid_trials = [tr for tr in trials_log if tr.get("status") == "ok"]
    if valid_trials:
        valid_trials.sort(
            key=lambda x: x["metrics"].get("net_pnl", -9999.0), reverse=True
        )
        top_entry = valid_trials[0]
        best_params = top_entry["params"]
        best_exit_dict = top_entry["exit_cfg"]
        best_metrics = top_entry["metrics"]
    elif trials_log:
        top_entry = trials_log[0]
        best_params = top_entry.get("params", {})
        best_exit_dict = top_entry.get("exit_cfg", {})
        best_metrics = top_entry.get("metrics", {})
    else:
        raise RuntimeError("Autotune produced no trial results")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    board_dir = root / "logs" / "research"
    board_dir.mkdir(parents=True, exist_ok=True)
    board_path = board_dir / f"autotune_{strategy_name}_{timeframe}_{stamp}.json"

    sampler_label = "optuna_tpe" if use_optuna else "karpathy_random_adaptive"
    board_path.write_text(
        json.dumps(
            {
                "strategy": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "lookback_days": lookback_days,
                "sampler_used": sampler_label,
                "fee_model": effective_fee_model,
                "n_trials": len(trials_log),
                "best_params": best_params,
                "best_exit_cfg": best_exit_dict,
                "best_metrics": best_metrics,
                "all_trials": trials_log,
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    export_dir: Path | None = None
    if not no_export:
        export_dir = _export_autotune_candidate(
            root=root,
            stamp=stamp,
            strategy_name=strategy_name,
            role=spec.role,
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            fee_model=effective_fee_model,
            provenance=provenance,
            best_params=best_params,
            best_exit_dict=best_exit_dict,
            best_metrics=best_metrics,
        )

    return AutotuneResult(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
        n_trials=len(trials_log),
        sampler_used=sampler_label,
        best_params=best_params,
        best_exit_cfg=best_exit_dict,
        best_metrics=best_metrics,
        export_dir=export_dir,
        board_path=board_path,
    )


# Backward compatibility alias
run_optuna_autotune = run_autotune
