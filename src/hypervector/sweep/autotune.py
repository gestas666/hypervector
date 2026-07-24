"""Karpathy & Optuna hybrid autotuning engine for strategy parameter optimization.

Implements two search strategies:
  1. Karpathy-style Random-Adaptive Autotune:
     - Stage 1: Coarse stochastic random search across continuous parameter space.
     - Stage 2: Elite candidate selection (top 10%) with Gaussian mutation / local zooming.
  2. Optuna TPE (Tree-structured Parzen Estimator):
     - Bayesian optimization with probabilistic density ratio modeling.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAVE_OPTUNA = True
except ImportError:
    HAVE_OPTUNA = False

from hypervector.data.pipeline import load_research_history
from hypervector.export import export_candidate
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import CostModel, resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import RiskConfig


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


def run_optuna_autotune(
    *,
    strategy_name: str = "crown_stack_long",
    symbol: str = "BTC",
    timeframe: str = "5m",
    lookback_days: int = 180,
    n_trials: int = 100,
    data_root: Path | str = "data",
    cost_preset: str = "hl_taker_default",
    export_best: bool = True,
    book_data_path: Path | str | None = None,
    sampler: str = "hybrid",  # "optuna" | "karpathy" | "hybrid"
) -> AutotuneResult:
    """Run Karpathy / Optuna parameter search over a strategy + exit configuration."""
    register_all_strategies()
    strategy_spec = get_strategy(strategy_name)
    root = Path(data_root)

    # 1. Load OHLCV data
    df, prov = load_research_history(
        root,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
    )

    # 2. Optional Orderbook Alignment if book_data_path provided
    if book_data_path is not None:
        p = Path(book_data_path)
        if p.is_file():
            from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl
            df_book = load_l2_jsonl(p)
            df = align_orderbook_to_ohlcv(df, df_book)

    cost = resolve_cost_model(cost_preset)
    close = df["close"].astype(float)

    trials_log: list[dict[str, Any]] = []

    def evaluate_config(params: dict[str, Any], exit_dict: dict[str, Any], trial_num: int) -> float:
        exit_cfg = ExitConfig(
            mode=exit_dict.get("mode", "atr"),  # type: ignore[arg-type]
            sl_atr_mult=float(exit_dict.get("sl_atr_mult", 1.5)),
            rr=float(exit_dict.get("rr", 2.0)),
            trail_atr_mult=float(exit_dict.get("trail_atr_mult", 2.0)),
            atr_length=14,
        )
        lev = float(exit_dict.get("leverage", 1.0))
        risk_cfg = RiskConfig(max_size_frac=lev)
        try:
            entries, exits, direction = strategy_spec.build_signals(df, **params)
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
            )

            trades = int(m.get("trades", 0))
            sharpe = float(m.get("sharpe", -99.0))
            net_pnl = float(m.get("net_pnl", -9999.0))
            max_dd = float(m.get("max_drawdown", 100.0))

            trials_log.append(
                {
                    "trial_number": trial_num,
                    "params": params,
                    "exit_cfg": exit_cfg.to_dict(),
                    "metrics": m,
                }
            )

            # Karpathy penalty score
            if trades < 10:
                return -50.0 + trades
            if max_dd > 25.0:
                return -20.0 - max_dd

            # Combined objective score
            return sharpe + (net_pnl / 1000.0)

        except Exception:
            return -999.0

    # Determine execution path based on sampler argument
    use_optuna = HAVE_OPTUNA and sampler in ("optuna", "hybrid")

    if use_optuna:
        def objective(trial: optuna.Trial) -> float:
            params: dict[str, Any] = {}
            if "crown" in strategy_name:
                params["bbwp_lookback"] = trial.suggest_categorical("bbwp_lookback", [100, 180, 252])
                params["bbwp_threshold"] = trial.suggest_float("bbwp_threshold", 10.0, 30.0, step=2.5)
                if "long" in strategy_name:
                    params["pmarp_exit_hi"] = trial.suggest_float("pmarp_exit_hi", 80.0, 98.0, step=2.0)
                else:
                    params["pmarp_exit_lo"] = trial.suggest_float("pmarp_exit_lo", 2.0, 20.0, step=2.0)
                params["regime_filter"] = trial.suggest_categorical("regime_filter", [True, False])

            elif "pine" in strategy_name or "trend_ride" in strategy_name:
                params["st_atr"] = trial.suggest_categorical("st_atr", [10, 14])
                params["st_mult"] = trial.suggest_float("st_mult", 2.0, 4.5, step=0.5)
                params["chop_max"] = trial.suggest_float("chop_max", 40.0, 60.0, step=5.0)
                params["zl_length"] = trial.suggest_categorical("zl_length", [50, 70, 90])
                params["use_squeeze"] = trial.suggest_categorical("use_squeeze", [True, False])
                params["regime_filter"] = trial.suggest_categorical("regime_filter", [True, False])
                if "long" in strategy_name:
                    params["pmarp_exit_hi"] = trial.suggest_float("pmarp_exit_hi", 85.0, 98.0, step=2.5)
                else:
                    params["pmarp_exit_lo"] = trial.suggest_float("pmarp_exit_lo", 2.0, 15.0, step=2.5)

            if "spread_bps" in df.columns or "obi_5" in df.columns or book_data_path is not None:
                params["book_gate"] = trial.suggest_categorical("book_gate", [True, False])
                params["max_spread_bps"] = trial.suggest_float("max_spread_bps", 1.5, 10.0, step=0.5)
                params["min_obi"] = trial.suggest_float("min_obi", -0.5, 0.4, step=0.1)

            # Suggest Exit & Leverage Configuration
            leverage = trial.suggest_categorical("leverage", [1.0, 2.0, 3.0, 5.0])
            exit_mode = trial.suggest_categorical("exit_mode", ["atr", "trail", "fixed_rr"])
            sl_atr_mult = trial.suggest_float("sl_atr_mult", 0.8, 4.0, step=0.4)
            rr = trial.suggest_float("rr", 1.2, 5.0, step=0.3)
            trail_atr_mult = trial.suggest_float("trail_atr_mult", 1.2, 5.0, step=0.3)
            sl_pct = trial.suggest_float("sl_pct", 0.003, 0.03, step=0.003)

            exit_dict = {
                "mode": exit_mode,
                "sl_pct": sl_pct,
                "sl_atr_mult": sl_atr_mult,
                "rr": rr,
                "trail_atr_mult": trail_atr_mult,
                "leverage": leverage,
                "max_size_frac": 0.1,
            }
            return evaluate_config(params, exit_dict, trial.number)

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    else:
        # Karpathy-style Random-Adaptive Autotune Engine
        rng = np.random.default_rng(42)
        best_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

        coarse_trials = max(5, int(n_trials * 0.6))
        fine_trials = n_trials - coarse_trials

        for t in range(n_trials):
            # Phase 1: Coarse random sampling across space
            # Phase 2: Adaptive mutation around elite candidates
            if t >= coarse_trials and best_candidates:
                # Select elite candidate
                elite_score, elite_params, elite_exit = best_candidates[rng.integers(0, min(3, len(best_candidates)))]
                params = dict(elite_params)
                exit_dict = dict(elite_exit)

                # Mutate continuous float parameters with small Gaussian noise
                for k, v in params.items():
                    if isinstance(v, float) and not isinstance(v, bool):
                        noise = float(rng.normal(0, abs(v) * 0.15))
                        params[k] = round(v + noise, 2)

                for k, v in exit_dict.items():
                    if isinstance(v, float):
                        noise = float(rng.normal(0, abs(v) * 0.15))
                        exit_dict[k] = round(max(0.5, v + noise), 2)
            else:
                params = {}
                if "crown" in strategy_name:
                    params["bbwp_lookback"] = int(rng.choice([100, 180, 252]))
                    params["bbwp_threshold"] = round(float(rng.uniform(10.0, 30.0)), 1)
                    if "long" in strategy_name:
                        params["pmarp_exit_hi"] = round(float(rng.uniform(80.0, 98.0)), 1)
                    else:
                        params["pmarp_exit_lo"] = round(float(rng.uniform(2.0, 20.0)), 1)
                    params["regime_filter"] = bool(rng.choice([True, False]))

                elif "pine" in strategy_name or "trend_ride" in strategy_name:
                    params["st_atr"] = int(rng.choice([10, 14]))
                    params["st_mult"] = round(float(rng.uniform(2.0, 4.5)), 1)
                    params["chop_max"] = round(float(rng.uniform(40.0, 60.0)), 1)
                    params["zl_length"] = int(rng.choice([50, 70, 90]))
                    params["use_squeeze"] = bool(rng.choice([True, False]))
                    params["regime_filter"] = bool(rng.choice([True, False]))
                    if "long" in strategy_name:
                        params["pmarp_exit_hi"] = round(float(rng.uniform(85.0, 98.0)), 1)
                    else:
                        params["pmarp_exit_lo"] = round(float(rng.uniform(2.0, 15.0)), 1)

                if "spread_bps" in df.columns or "obi_5" in df.columns or book_data_path is not None:
                    params["book_gate"] = bool(rng.choice([True, False]))
                    params["max_spread_bps"] = round(float(rng.uniform(1.5, 10.0)), 1)
                    params["min_obi"] = round(float(rng.uniform(-0.5, 0.4)), 1)

                exit_dict = {
                    "mode": str(rng.choice(["atr", "trail", "fixed_rr"])),
                    "sl_atr_mult": round(float(rng.uniform(1.0, 3.5)), 1),
                    "rr": round(float(rng.uniform(1.5, 4.0)), 1),
                    "trail_atr_mult": round(float(rng.uniform(1.5, 4.0)), 1),
                }

            score = evaluate_config(params, exit_dict, t)
            if score > -50.0:
                best_candidates.append((score, params, exit_dict))
                best_candidates.sort(key=lambda x: x[0], reverse=True)
                best_candidates = best_candidates[:5]  # Keep top 5 elite

    # Process best trial results
    if trials_log:
        trials_log.sort(key=lambda x: x["metrics"].get("sharpe", -99.0), reverse=True)
        top_entry = trials_log[0]
        best_params = top_entry["params"]
        best_exit_dict = top_entry["exit_cfg"]
        best_metrics = top_entry["metrics"]
    else:
        raise RuntimeError("Autotune produced no valid trial results")

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
                "n_trials": len(trials_log),
                "best_params": best_params,
                "best_exit_cfg": best_exit_dict,
                "best_metrics": best_metrics,
                "top_trials": trials_log[:10],
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    export_path: Path | None = None
    if export_best and best_metrics.get("net_pnl", -1) > 0:
        cand_id = f"export_autotuned_{strategy_name}_{stamp}"
        export_path = export_candidate(
            root / "exports",
            run_id=cand_id,
            meta={
                "strategy": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "lookback_days": lookback_days,
                "autotune": True,
                "sampler_used": sampler_label,
            },
            params={**best_params, **best_exit_dict, "strategy": strategy_name},
            metrics=best_metrics,
            strict=False,
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
        export_dir=export_path,
        board_path=board_path,
    )
