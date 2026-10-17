"""Karpathy and optional Optuna orchestration over explicit research inputs."""

from __future__ import annotations

from functools import partial
from pathlib import Path
import pandas as pd

from hypervector.data.pipeline import load_research_history
from hypervector.strategies import register_all_strategies
from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.autotune_models import (
    AutotuneResult as AutotuneResult,
    SearchSettings,
)
from hypervector.sweep.autotune_evaluation import TrialEvaluator
from hypervector.sweep.autotune_search import (
    SamplingTools,
    run_karpathy,
    optuna_objective,
)
from hypervector.sweep.autotune_artifacts import finish_search
from hypervector.sweep.autotune_export import (
    _export_autotune_candidate as _export_autotune_candidate,
)
from hypervector.sweep.autotune_sampling import (
    _sample_grid_params as _sample_grid_params,
    _mutate_grid_params as _mutate_grid_params,
    _clamp_strategy_leverage as _clamp_strategy_leverage,
    _hypervelocity_exit_dict as _hypervelocity_exit_dict,
    _random_exit_dict as _random_exit_dict,
    _optuna_exit_dict as _optuna_exit_dict,
)

try:
    import optuna
except ImportError:
    optuna = None
HAVE_OPTUNA = optuna is not None


def run_autotune(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
    symbol: str = "BTC",
    timeframe: str = "5m",
    lookback_days: int = 180,
    strategy_name: str = "crown_stack_long",
    n_trials: int = 100,
    fee_model: str = "hl_base_taker",
    book_data_path: str | Path | None = None,
    sampler: str = "karpathy",
    strict_hl_only: bool = False,
    force_refresh: bool = False,
    no_export: bool = False,
    export_best: bool = True,
    apply_penalties: bool = False,
) -> AutotuneResult:
    """Run a measured search; abort technical failures without rejecting weak trials."""
    if type(n_trials) is not int or n_trials <= 0:
        raise ValueError("n_trials must be a positive integer")
    if sampler not in {"karpathy", "optuna", "hybrid"}:
        raise ValueError(f"unsupported autotune sampler: {sampler}")
    if sampler in {"optuna", "hybrid"} and not HAVE_OPTUNA:
        raise RuntimeError(
            "Optuna sampler requested: install hypervector[optuna] or select --sampler karpathy"
        )
    settings = SearchSettings(
        Path(root or data_root or Path.cwd()),
        strategy_name,
        symbol,
        timeframe,
        lookback_days,
        n_trials,
        "hl_maker" if is_hypervelocity_strategy(strategy_name) else fee_model,
        book_data_path,
        sampler,
        no_export or not export_best,
        apply_penalties,
        strict_hl_only,
        force_refresh,
    )
    return _run_search(settings)


def _load_inputs(settings: SearchSettings) -> tuple[pd.DataFrame, dict[str, object]]:
    bars, provenance = load_research_history(
        settings.root,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        lookback_days=settings.lookback_days,
        strict_hl_only=settings.strict_hl_only,
        force_refresh=settings.force_refresh,
    )
    if bars.empty:
        raise RuntimeError(
            f"No research history found for {settings.symbol} {settings.timeframe}"
        )
    if settings.book_data_path and Path(settings.book_data_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

        bars = align_orderbook_to_ohlcv(bars, load_l2_jsonl(settings.book_data_path))
    return bars, provenance


def _run_search(settings: SearchSettings) -> AutotuneResult:
    register_all_strategies()
    bars, provenance = _load_inputs(settings)
    strategy = get_strategy(settings.strategy_name)
    evaluator = TrialEvaluator(
        bars,
        strategy,
        "short" if "short" in settings.strategy_name.lower() else "long",
        resolve_cost_model(settings.fee_model),
        is_hypervelocity_strategy(settings.strategy_name),
        compute_trial_metrics,
        settings.apply_penalties,
    )
    tools = SamplingTools(
        _sample_grid_params,
        _mutate_grid_params,
        _random_exit_dict,
        _optuna_exit_dict,
        _clamp_strategy_leverage,
    )
    if settings.sampler == "karpathy":
        run_karpathy(settings, evaluator, tools)
    else:
        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=42)
        )
        study.optimize(
            partial(optuna_objective, settings, evaluator, tools),
            n_trials=settings.n_trials,
            show_progress_bar=False,
        )
    return finish_search(
        settings,
        trials=evaluator.trials,
        role=strategy.role,
        provenance=provenance,
        exporter=_export_autotune_candidate,
    )


run_optuna_autotune = run_autotune
