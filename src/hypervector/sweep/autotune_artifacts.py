"""Durable trial boards and strict exports from successful searches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

from hypervector.sweep.autotune_evaluation import selection_key, sharpe_defined
from hypervector.sweep.autotune_models import (
    SEARCH_SEED,
    SELECTION_IN_SAMPLE,
    SELECTION_TRAIN_ONLY,
    AutotuneResult,
    SearchSettings,
)
from hypervector.sweep.autotune_provenance import code_identity

BOARD_SCHEMA = "autotune_board/v2"
logger = logging.getLogger(__name__)
HoldoutMeasure = Callable[[dict[str, object], dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class BoardContext:
    """Search facts the board records beyond the trials themselves."""

    data_window: dict[str, object] = field(default_factory=dict)
    train_window: dict[str, object] | None = None
    holdout_window: dict[str, object] | None = None
    search_space: dict[str, object] = field(default_factory=dict)
    costs: dict[str, object] = field(default_factory=dict)
    book_data_loaded: bool = False
    space_exhausted: bool = False
    duplicate_resamples: int = 0
    warnings: tuple[str, ...] = ()
    #: Normalised trade direction the builder reported (None if no trial ran).
    direction: str | None = None


@dataclass(frozen=True)
class _Selection:
    best: dict[str, object]
    train_metrics: dict[str, object]
    holdout_metrics: dict[str, object] | None
    holdout_error: str | None
    selection_basis: str
    evaluation_window: str
    best_metrics: dict[str, object]
    #: The selected trial re-measured on every bar, only when ``best_metrics``
    #: cover the holdout alone: the like-for-like VectorBT figure for engine
    #: parity (Nautilus replays the whole window). In-sample; never a gate.
    full_window_metrics: dict[str, object] | None = None
    full_window_error: str | None = None


def sampler_label(sampler: str) -> str:
    """Name the search algorithm that actually ran."""
    return "karpathy_random_adaptive" if sampler == "karpathy" else "optuna_tpe"


def finish_search(
    settings: SearchSettings,
    *,
    trials: list[dict[str, object]],
    role: str,
    provenance: dict[str, object],
    exporter: Callable[..., Path],
    holdout: HoldoutMeasure | None = None,
    context: BoardContext | None = None,
    full_window: HoldoutMeasure | None = None,
) -> AutotuneResult:
    """Preserve error evidence and refuse to call an all-failed search successful.

    The best trial is chosen by the same objective the search maximised. When
    a holdout measure is given, the chosen trial is measured once out of
    sample; both windows are reported and neither is a gate. ``full_window``
    then re-measures that trial on every bar, so engine parity can compare
    like with like.
    """
    context = context or BoardContext()
    valid = [trial for trial in trials if trial["status"] == "ok"]
    valid.sort(key=lambda trial: selection_key(trial, settings.objective), reverse=True)
    selection = _with_full_window(_select(settings, valid, holdout), full_window)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    label = sampler_label(settings.sampler)
    warnings = _warnings(settings, trials, valid, selection, context)
    for note in warnings:  # report-only; surfaces on stderr for CLI runs
        logger.warning("Autotune: %s", note)
    board_path = _publish_board(
        settings,
        trials,
        selection,
        stamp,
        label,
        provenance=provenance,
        context=context,
        warnings=warnings,
    )
    if not valid:
        raise RuntimeError(
            f"Autotune produced no successful trials; inspect technical failures: {board_path}"
        )
    best = selection.best
    evaluation = _evaluation(settings, selection, context, board_path)
    # Label the reported metrics wherever they go (export, result, CLI JSON):
    # they are holdout metrics when a holdout exists, in-sample otherwise.
    best_metrics = {
        **selection.best_metrics,
        "evaluation_window": selection.evaluation_window,
        "selection_basis": selection.selection_basis,
    }
    export_dir = (
        None
        if settings.no_export
        else exporter(
            root=settings.root,
            stamp=stamp,
            strategy_name=settings.strategy_name,
            role=role,
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            lookback_days=settings.lookback_days,
            fee_model=settings.fee_model,
            fee_model_requested=settings.requested_fee_model,
            provenance=provenance,
            best_params=best["params"],
            best_exit_dict=best["exit_cfg"],
            best_metrics=best_metrics,
            evaluation=evaluation,
        )
    )
    return AutotuneResult(
        settings.strategy_name,
        settings.symbol,
        settings.timeframe,
        settings.lookback_days,
        len(trials),
        label,
        best["params"],  # type: ignore[arg-type]
        best["exit_cfg"],  # type: ignore[arg-type]
        best_metrics,
        export_dir,
        board_path,
        objective=settings.objective,
        selection_basis=selection.selection_basis,
        train_metrics=selection.train_metrics,
        holdout_metrics=selection.holdout_metrics,
        best_trial_number=best.get("trial_number"),  # type: ignore[arg-type]
        best_trade_count=_trade_count(selection.train_metrics),
        n_trials_requested=settings.n_trials,
        space_exhausted=context.space_exhausted,
        warnings=warnings,
        fee_model_used=settings.fee_model,
        fee_model_requested=settings.requested_fee_model,
    )


def cache_policy(settings: SearchSettings) -> dict[str, object]:
    """The history freshness the search loaded under (board provenance)."""
    if settings.pin_cache:
        mode = "pinned"
    elif settings.max_cache_age_hours is not None:
        mode = "max_age"
    else:
        mode = "loader_default"
    return {
        "mode": mode,
        "pin_cache": settings.pin_cache,
        "max_cache_age_hours": settings.max_cache_age_hours,
        "force_refresh": settings.force_refresh,
    }


def _select(
    settings: SearchSettings,
    valid: list[dict[str, object]],
    holdout: HoldoutMeasure | None,
) -> _Selection:
    has_holdout = settings.train_fraction < 1.0
    basis = SELECTION_TRAIN_ONLY if has_holdout else SELECTION_IN_SAMPLE
    if not valid:
        empty: dict[str, object] = {}
        best: dict[str, object] = {
            "trial_number": None,
            "params": {},
            "exit_cfg": {},
            "metrics": {},
        }
        return _Selection(best, empty, None, None, basis, basis, empty)
    best = valid[0]
    train_metrics = best["metrics"]
    assert isinstance(train_metrics, dict)
    if not has_holdout or holdout is None:
        return _Selection(
            best, train_metrics, None, None, basis, SELECTION_IN_SAMPLE, train_metrics
        )
    try:
        holdout_metrics = holdout(best["params"], best["exit_cfg"])  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - report the holdout's technical failure
        error = f"{type(exc).__name__}: {exc}"
        return _Selection(
            best, train_metrics, None, error, basis, "train_in_sample", train_metrics
        )
    return _Selection(
        best, train_metrics, holdout_metrics, None, basis, "holdout", holdout_metrics
    )


def _with_full_window(
    selection: _Selection, measure: HoldoutMeasure | None
) -> _Selection:
    """Add the selected trial's full-window metrics when it was scored on the holdout."""
    if measure is None or selection.evaluation_window != "holdout":
        return selection
    try:
        metrics = measure(selection.best["params"], selection.best["exit_cfg"])  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - report-only, like the holdout measure
        return replace(selection, full_window_error=f"{type(exc).__name__}: {exc}")
    return replace(selection, full_window_metrics=metrics)


def _trade_count(metrics: dict[str, object]) -> int | None:
    value = metrics.get("trade_count", metrics.get("trades"))
    try:
        return None if value is None else int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _warnings(
    settings: SearchSettings,
    trials: list[dict[str, object]],
    valid: list[dict[str, object]],
    selection: _Selection,
    context: BoardContext,
) -> list[str]:
    """Report-only observations; none of them rejects a trial or an export."""
    warnings = list(context.warnings)
    errors = len(trials) - len(valid)
    if errors:
        warnings.append(
            f"{errors} of {len(trials)} trials failed technically; see all_trials errors"
        )
    zero = sum(not sharpe_defined(trial["metrics"]) for trial in valid)  # type: ignore[arg-type]
    if zero:
        warnings.append(
            f"{zero} of {len(valid)} successful trials had zero trades (Sharpe undefined)"
        )
    if valid and _trade_count(selection.train_metrics) == 0:
        warnings.append(
            "selected trial has zero trades; its metrics measure inactivity, not edge"
        )
    if selection.holdout_metrics is not None and _trade_count(selection.holdout_metrics) == 0:
        warnings.append("holdout measurement of the selected trial has zero trades")
    if selection.holdout_error is not None:
        warnings.append(
            f"holdout evaluation failed ({selection.holdout_error}); "
            "best_metrics are in-sample training metrics"
        )
    if context.space_exhausted:
        warnings.append(
            f"search space exhausted after {len(trials)} unique configurations "
            f"({settings.n_trials} requested)"
        )
    return warnings


def _evaluation(
    settings: SearchSettings,
    selection: _Selection,
    context: BoardContext,
    board_path: Path,
) -> dict[str, object]:
    return {
        "objective": settings.objective,
        "selection_basis": selection.selection_basis,
        "evaluation_window": selection.evaluation_window,
        "train_fraction": settings.train_fraction,
        "train_window": context.train_window or context.data_window,
        "holdout_window": context.holdout_window,
        "full_window": context.data_window,
        "train_metrics": selection.train_metrics,
        "holdout_metrics": selection.holdout_metrics,
        "holdout_error": selection.holdout_error,
        "full_window_metrics": selection.full_window_metrics,
        "full_window_error": selection.full_window_error,
        "best_trial_number": selection.best.get("trial_number"),
        "board_path": str(board_path),
    }


def _finite_or_none(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _publish_board(
    settings: SearchSettings,
    trials: list[dict[str, object]],
    selection: _Selection,
    stamp: str,
    sampler: str,
    *,
    provenance: dict[str, object],
    context: BoardContext,
    warnings: list[str],
) -> Path:
    directory = settings.root / "logs" / "research"
    directory.mkdir(parents=True, exist_ok=True)
    target = (
        directory
        / f"autotune_{settings.strategy_name}_{settings.timeframe}_{stamp}.json"
    )
    valid = [trial for trial in trials if trial["status"] == "ok"]
    document = {
        "schema": BOARD_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": settings.strategy_name,
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "lookback_days": settings.lookback_days,
        "sampler_requested": settings.sampler_requested or settings.sampler,
        "sampler_used": sampler,
        "seed": SEARCH_SEED,
        "objective": settings.objective,
        "selection_basis": selection.selection_basis,
        "evaluation_window": selection.evaluation_window,
        "train_fraction": settings.train_fraction,
        "fee_model": settings.fee_model,
        "fee_model_used": settings.fee_model,
        "fee_model_requested": settings.requested_fee_model,
        "fee_model_overridden": settings.fee_model_requested is not None,
        "direction": context.direction,
        "costs": context.costs,
        "n_trials": len(trials),
        "n_trials_requested": settings.n_trials,
        "unique_configs": sum("duplicate_of" not in trial for trial in trials),
        "space_exhausted": context.space_exhausted,
        "duplicate_resamples": context.duplicate_resamples,
        "error_trials": len(trials) - len(valid),
        "zero_trade_trials": sum(
            not sharpe_defined(trial["metrics"]) for trial in valid  # type: ignore[arg-type]
        ),
        "strict_hl_only": settings.strict_hl_only,
        "force_refresh": settings.force_refresh,
        "cache_policy": cache_policy(settings),
        "book_data_path": (
            None if settings.book_data_path is None else str(settings.book_data_path)
        ),
        "book_data_loaded": context.book_data_loaded,
        "search_space": context.search_space,
        "data_provenance": provenance,
        "data_window": context.data_window,
        "train_window": context.train_window,
        "holdout_window": context.holdout_window,
        "code_identity": code_identity(),
        "best_trial_number": selection.best.get("trial_number"),
        "best_params": selection.best["params"],
        "best_exit_cfg": selection.best["exit_cfg"],
        "best_metrics": selection.best_metrics,
        "best_train_metrics": selection.train_metrics,
        "best_holdout_metrics": selection.holdout_metrics,
        "holdout_error": selection.holdout_error,
        "best_full_window_metrics": selection.full_window_metrics,
        "full_window_error": selection.full_window_error,
        "best_trade_count": _trade_count(selection.train_metrics),
        "warnings": warnings,
        "all_trials": [
            {key: _finite_or_none(value) for key, value in trial.items()}
            for trial in trials
        ],
    }
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, default=str) + "\n")
    return target
