"""Autotune command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def cmd_autotune(args: argparse.Namespace) -> int:
    """Run Optuna / Karpathy autotuning for strategy optimization."""
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
        book_data_path=getattr(args, "book_path", None),
        sampler=getattr(args, "sampler", "karpathy"),
        strict_hl_only=args.strict_hl_only,
        force_refresh=args.force,
    )
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
        "export_dir": str(res.export_dir) if res.export_dir else None,
        "board_path": str(res.board_path),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0
