"""Autotune command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
import math
from pathlib import Path
import sys

from hypervector.commands.common import CommandRefused, cache_age_options


def cmd_autotune(args: argparse.Namespace) -> int:
    """Run Karpathy (or optional Optuna TPE) autotuning for one strategy.

    A non-positive ``--n-trials``, an unavailable sampler, an unknown strategy
    or objective, a train fraction outside (0, 1], a missing book file or
    contradictory cache flags (``--pin-cache`` with ``--max-cache-age-hours``
    or ``--refresh``) is refused (exit 2) before any data load; an all-failed
    search is a technical failure (exit 1). The search
    covers the first ``--train-fraction`` of bars and the selected trial is
    measured once on the remaining holdout (report-only, never a gate).
    """
    n_trials = getattr(args, "n_trials", None)
    if type(n_trials) is not int or n_trials < 1:
        raise CommandRefused("--n-trials must be at least 1")
    sampler = getattr(args, "sampler", "karpathy")
    if sampler == "optuna" and find_spec("optuna") is None:
        raise CommandRefused(
            "--sampler optuna needs the optional 'optuna' package "
            "(install hypervector[optuna]) or use --sampler karpathy"
        )
    book_path = getattr(args, "book_path", None)
    if book_path and not Path(book_path).is_file():
        raise CommandRefused(f"book path not found: {book_path}")
    objective = str(getattr(args, "objective", "net_pnl"))
    train_fraction = float(getattr(args, "train_fraction", 0.7))
    if not (math.isfinite(train_fraction) and 0.0 < train_fraction <= 1.0):
        raise CommandRefused("--train-fraction must be in (0, 1]")
    cache_age_options(args)  # refuses contradictory cache flags (exit 2)
    pin_cache = getattr(args, "pin_cache", False) is True
    max_cache_age_hours = getattr(args, "max_cache_age_hours", None)
    _require_registered_strategy(args.strategy)

    from hypervector.sweep.autotune import run_optuna_autotune
    from hypervector.sweep.autotune_models import OBJECTIVES

    if objective not in OBJECTIVES:
        raise CommandRefused(
            f"unknown --objective {objective!r}; choose one of {', '.join(OBJECTIVES)}"
        )
    res = run_optuna_autotune(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.lookback,
        n_trials=args.n_trials,
        data_root=Path(args.data_root),
        fee_model=args.fee_model,
        export_best=not args.no_export,
        book_data_path=book_path,
        sampler=sampler,
        strict_hl_only=args.strict_hl_only,
        force_refresh=args.force,
        objective=objective,
        train_fraction=train_fraction,
        pin_cache=pin_cache,
        max_cache_age_hours=max_cache_age_hours,
    )
    export_dir = str(res.export_dir) if res.export_dir else None
    warnings = list(getattr(res, "warnings", []) or [])
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    out = {
        "ok": True,
        "strategy": res.strategy_name,
        "symbol": res.symbol,
        "timeframe": res.timeframe,
        "lookback_days": res.lookback_days,
        "n_trials": res.n_trials,
        "n_trials_requested": getattr(res, "n_trials_requested", None),
        "space_exhausted": getattr(res, "space_exhausted", None),
        "sampler_used": res.sampler_used,
        "fee_model_requested": getattr(res, "fee_model_requested", None) or args.fee_model,
        "fee_model_used": getattr(res, "fee_model_used", None) or args.fee_model,
        "objective": getattr(res, "objective", objective),
        "train_fraction": train_fraction,
        "selection_basis": getattr(res, "selection_basis", None),
        "best_trial_number": getattr(res, "best_trial_number", None),
        "best_trade_count": getattr(res, "best_trade_count", None),
        "best_params": res.best_params,
        "best_exit_cfg": res.best_exit_cfg,
        "best_metrics": res.best_metrics,
        "train_metrics": getattr(res, "train_metrics", None),
        "holdout_metrics": getattr(res, "holdout_metrics", None),
        "warnings": warnings,
        "export_dir": export_dir,
        "candidate_id": Path(export_dir).name if export_dir else None,
        "board_path": str(res.board_path),
        "artifacts": {"board": str(res.board_path), "export": export_dir},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _require_registered_strategy(name: str) -> None:
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy

    register_all_strategies()
    try:
        get_strategy(name)
    except KeyError as exc:
        raise CommandRefused(f"unknown strategy: {name}") from exc
