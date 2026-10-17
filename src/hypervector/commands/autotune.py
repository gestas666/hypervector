"""Autotune command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
from pathlib import Path

from hypervector.commands.common import CommandRefused


def cmd_autotune(args: argparse.Namespace) -> int:
    """Run Karpathy (or optional Optuna TPE) autotuning for one strategy.

    An unavailable sampler or unknown strategy is refused (exit 2) before any
    data load; an all-failed search is a technical failure (exit 1).
    """
    sampler = getattr(args, "sampler", "karpathy")
    if sampler == "optuna" and find_spec("optuna") is None:
        raise CommandRefused(
            "--sampler optuna needs the optional 'optuna' package "
            "(install hypervector[optuna]) or use --sampler karpathy"
        )
    book_path = getattr(args, "book_path", None)
    if book_path and not Path(book_path).is_file():
        raise CommandRefused(f"book path not found: {book_path}")
    _require_registered_strategy(args.strategy)

    from hypervector.sweep.autotune import run_optuna_autotune

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
    )
    export_dir = str(res.export_dir) if res.export_dir else None
    out = {
        "ok": True,
        "strategy": res.strategy_name,
        "symbol": res.symbol,
        "timeframe": res.timeframe,
        "lookback_days": res.lookback_days,
        "n_trials": res.n_trials,
        "sampler_used": res.sampler_used,
        "best_params": res.best_params,
        "best_exit_cfg": res.best_exit_cfg,
        "best_metrics": res.best_metrics,
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
