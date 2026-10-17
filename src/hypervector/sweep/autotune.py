"""Karpathy and optional Optuna orchestration over explicit research inputs."""

from __future__ import annotations

from functools import partial
import math
from pathlib import Path
import pandas as pd

from hypervector.config import DEFAULT_LOOKBACK, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from hypervector.data.pipeline import load_research_history
from hypervector.strategies import register_all_strategies
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    is_hypervelocity_strategy,
)
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.autotune_models import (
    AutotuneResult as AutotuneResult,
    DEFAULT_OBJECTIVE,
    DEFAULT_TRAIN_FRACTION,
    OBJECTIVES,
    SEARCH_SEED,
    SearchSettings,
)
from hypervector.sweep.autotune_evaluation import TrialEvaluator
from hypervector.sweep.autotune_search import (
    BOOK_COLUMNS,
    SamplingTools,
    SearchStats,
    run_karpathy,
    optuna_objective,
    searches_book_dimensions,
)
from hypervector.sweep.autotune_artifacts import BoardContext, finish_search
from hypervector.sweep.autotune_export import (
    _export_autotune_candidate as _export_autotune_candidate,
)
from hypervector.sweep.autotune_provenance import bars_window
from hypervector.sweep.autotune_sampling import (
    _sample_grid_params as _sample_grid_params,
    _mutate_grid_params as _mutate_grid_params,
    _clamp_strategy_leverage as _clamp_strategy_leverage,
    _hypervelocity_exit_dict as _hypervelocity_exit_dict,
    _random_exit_dict as _random_exit_dict,
    _optuna_exit_dict as _optuna_exit_dict,
    exit_space,
    venue_leverage_cap,
)

try:
    import optuna
except ImportError:
    optuna = None
HAVE_OPTUNA = optuna is not None
_SQLITE_BOOK_SUFFIXES = frozenset({".sqlite", ".sqlite3", ".db", ".zst"})
_HYBRID_NOTE = "sampler 'hybrid' is a deprecated alias of optuna TPE"


def run_autotune(
    root: Path | None = None,
    *,
    data_root: Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    lookback_days: int = DEFAULT_LOOKBACK,
    strategy_name: str = "crown_stack_long",
    n_trials: int = 100,
    fee_model: str = "hl_base_taker",
    book_data_path: str | Path | None = None,
    sampler: str = "karpathy",
    strict_hl_only: bool = False,
    force_refresh: bool = False,
    no_export: bool = False,
    export_best: bool = True,
    objective: str = DEFAULT_OBJECTIVE,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
) -> AutotuneResult:
    """Run a measured search; abort technical failures without rejecting weak trials.

    Defaults mirror ``tune strategy`` (BTC, 1m, 90 days, hl_base_taker).
    ``data_root`` is required so logs/ and exports/ never land in the CWD.
    Trials are searched on the first ``train_fraction`` of bars; the chosen
    configuration is then measured once on the remaining chronological
    holdout (``train_fraction=1.0`` keeps the labelled in-sample mode).
    """
    if type(n_trials) is not int or n_trials <= 0:
        raise ValueError("n_trials must be a positive integer")
    if sampler not in {"karpathy", "optuna", "hybrid"}:
        raise ValueError(f"unsupported autotune sampler: {sampler}")
    if sampler in {"optuna", "hybrid"} and not HAVE_OPTUNA:
        raise RuntimeError(
            "Optuna sampler requested: install hypervector[optuna] or select --sampler karpathy"
        )
    if objective not in OBJECTIVES:
        raise ValueError(
            f"unsupported autotune objective {objective!r}; choose one of {', '.join(OBJECTIVES)}"
        )
    if not (
        isinstance(train_fraction, (int, float))
        and math.isfinite(train_fraction)
        and 0.0 < train_fraction <= 1.0
    ):
        raise ValueError("train_fraction must be in (0, 1]")
    selected_root = _resolve_root(root, data_root)
    if book_data_path not in (None, "") and not Path(book_data_path).is_file():  # type: ignore[arg-type]
        raise FileNotFoundError(f"book data path is not a file: {book_data_path}")
    hypervelocity = is_hypervelocity_strategy(strategy_name)
    if hypervelocity:
        _check_hypervelocity_leverage(symbol)
    settings = SearchSettings(
        root=selected_root,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        lookback_days=lookback_days,
        n_trials=n_trials,
        fee_model="hl_maker" if hypervelocity else fee_model,
        book_data_path=book_data_path or None,
        sampler="optuna" if sampler == "hybrid" else sampler,
        no_export=no_export or not export_best,
        strict_hl_only=strict_hl_only,
        force_refresh=force_refresh,
        objective=objective,
        train_fraction=float(train_fraction),
        sampler_requested=sampler,
    )
    return _run_search(settings)


def _resolve_root(root: Path | None, data_root: Path | None) -> Path:
    if root is not None and data_root is not None and Path(root) != Path(data_root):
        raise ValueError("root and data_root disagree; pass only data_root")
    selected = data_root if data_root is not None else root
    if selected is None:
        raise ValueError("data_root is required (the CLI default is ./data)")
    return Path(selected)


def _check_hypervelocity_leverage(symbol: str) -> None:
    """The fixed Hypervelocity contract cannot run above a venue's leverage cap."""
    required = HypervelocityContract().leverage
    cap = venue_leverage_cap(symbol)
    if required > cap:
        raise ValueError(
            f"Hypervelocity's fixed {required:g}x contract leverage exceeds the "
            f"{symbol} venue leverage cap of {cap:g}x"
        )


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
    if settings.book_data_path:
        from hypervector.data import book_align

        path = Path(settings.book_data_path)
        book = (
            book_align.load_l2_sqlite_feature_samples(path, coin=settings.symbol)
            if path.suffix.lower() in _SQLITE_BOOK_SUFFIXES
            else book_align.load_l2_jsonl(path)
        )
        bars = book_align.align_orderbook_to_ohlcv(bars, book)
    return bars, provenance


def _train_cut(bars: pd.DataFrame, train_fraction: float) -> int:
    if train_fraction >= 1.0:
        return len(bars)
    cut = int(len(bars) * train_fraction)
    if cut < 2 or len(bars) - cut < 2:
        raise ValueError(
            f"train_fraction={train_fraction} leaves {cut} training and "
            f"{len(bars) - cut} holdout bars; each needs at least 2"
        )
    return cut


def _run_search(settings: SearchSettings) -> AutotuneResult:
    register_all_strategies()
    bars, provenance = _load_inputs(settings)
    strategy = get_strategy(settings.strategy_name)
    hypervelocity = is_hypervelocity_strategy(settings.strategy_name)
    cut = _train_cut(bars, settings.train_fraction)
    direction = "short" if "short" in settings.strategy_name.lower() else "long"
    cost = resolve_cost_model(settings.fee_model)

    def evaluator_for(frame: pd.DataFrame) -> TrialEvaluator:
        return TrialEvaluator(
            frame,
            strategy,
            direction,
            cost,
            hypervelocity,
            compute_trial_metrics,
            objective=settings.objective,
            # Venue cap and maintenance margin of the traded symbol, as in
            # 'backtest run' and 'backtest sweep'.
            symbol=settings.symbol,
        )

    evaluator = evaluator_for(bars.iloc[:cut] if cut < len(bars) else bars)
    tools = SamplingTools(
        _sample_grid_params,
        _mutate_grid_params,
        _random_exit_dict,
        _optuna_exit_dict,
        _clamp_strategy_leverage,
    )
    book_requested = bool(settings.book_data_path)
    book_loaded = book_requested and BOOK_COLUMNS.issubset(bars.columns)
    book_dimensions = settings.sampler != "karpathy" and searches_book_dimensions(evaluator)
    notes: list[str] = []
    if settings.sampler_requested == "hybrid":
        notes.append(_HYBRID_NOTE)
    if book_requested and not book_loaded:
        notes.append(
            "book data path given but alignment produced no spread_bps/obi_5 "
            "columns; book dimensions were not searched"
        )
    elif book_loaded and not bool(getattr(strategy, "supports_book_gate", False)):
        notes.append(
            f"book data loaded but {settings.strategy_name} does not declare book "
            "gating; book dimensions were not searched"
        )
    elif book_loaded and settings.sampler == "karpathy":
        notes.append("book data loaded; the karpathy sampler does not search book dimensions")
    if settings.sampler == "karpathy":
        stats = run_karpathy(settings, evaluator, tools)
    else:
        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEARCH_SEED)
        )
        study.optimize(
            partial(optuna_objective, settings, evaluator, tools),
            n_trials=settings.n_trials,
            show_progress_bar=False,
        )
        stats = SearchStats()
    measure_holdout = None
    if cut < len(bars):
        full = evaluator_for(bars)

        def measure_holdout(
            params: dict[str, object], exits: dict[str, object]
        ) -> dict[str, object]:
            # Signals see every bar (causal warmup); only bars[cut:] are scored.
            metrics, _ = full.measure(params, exits, evaluation_start=cut)
            return metrics

    context = BoardContext(
        data_window=bars_window(bars),
        train_window=bars_window(bars.iloc[:cut]) if cut < len(bars) else None,
        holdout_window=bars_window(bars.iloc[cut:]) if cut < len(bars) else None,
        search_space={
            "param_grid": strategy.param_grid,
            "exit_space": exit_space(hypervelocity=hypervelocity, sampler=settings.sampler),
            "book_dimensions": book_dimensions,
        },
        costs=cost.to_dict(),
        book_data_loaded=book_loaded,
        space_exhausted=stats.space_exhausted,
        duplicate_resamples=stats.duplicate_resamples,
        warnings=tuple(notes),
    )
    return finish_search(
        settings,
        trials=evaluator.trials,
        role=strategy.role,
        provenance=provenance,
        exporter=_export_autotune_candidate,
        holdout=measure_holdout,
        context=context,
    )


run_optuna_autotune = run_autotune
