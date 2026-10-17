"""Backtest command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import pandas as pd
from pathlib import Path
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.sizing import RiskConfig
from hypervector.commands.common import _load_bars


def cmd_backtest(args: argparse.Namespace) -> int:
    """Run Phase-1.5 backtest across any registered strategy with leverage & fee models."""
    from hypervector.sweep.metrics import compute_trial_metrics

    register_all_strategies()
    df_bars = _backtest_bars(args)

    spec = get_strategy(args.strategy)
    params = {}
    if getattr(args, "book_gate", False):
        params["book_gate"] = True
        params["max_spread_bps"] = getattr(args, "max_spread_bps", 3.0)
        params["min_obi"] = getattr(args, "min_obi", 0.1)

    entries, exits, direction = spec.build_signals(df_bars, **params)
    close = df_bars["close"].astype(float)

    exit_cfg = ExitConfig(
        mode=args.exit_mode,
        sl_atr_mult=args.sl_atr_mult,
        rr=args.rr,
    )
    risk_cfg = RiskConfig(max_size_frac=args.leverage)
    cost = resolve_cost_model(args.fee_model)

    direction_clean = "short" if "short" in str(direction).lower() else "long"

    m = compute_trial_metrics(
        close,
        entries,
        exits,
        direction=direction_clean,
        init_cash=args.init_cash,
        df=df_bars,
        cost=cost,
        exit_cfg=exit_cfg,
        risk_cfg=risk_cfg,
    )

    out = _backtest_report(args, m)
    print(json.dumps(out, indent=2, default=str))
    return 0


def _backtest_report(
    args: argparse.Namespace, m: dict[str, object]
) -> dict[str, object]:
    """Format measured backtest metrics without introducing performance gates."""
    return {
        "ok": True,
        "strategy": args.strategy,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "lookback_days": args.lookback,
        "leverage": args.leverage,
        "initial_cash": args.init_cash,
        "fee_model": args.fee_model,
        "orderbook_gated": getattr(args, "book_gate", False),
        "metrics": {
            "net_pnl": round(m["net_pnl"], 2),
            "total_return_pct": round(m["total_return_pct"], 2),
            "sharpe_annualized": round(m["sharpe"], 2),
            "max_drawdown_pct": round(m["max_drawdown"], 2),
            "total_trades": m["trade_count"],
            "wins": m["wins"],
            "losses": m["losses"],
            "win_pct": round(m["win_pct"], 1),
            "profit_factor": round(m["profit_factor"], 2)
            if m.get("profit_factor") is not None
            else None,
            "avg_trade_pnl": round(m["net_pnl"] / m["trade_count"], 2)
            if m["trade_count"] > 0
            else 0.0,
        },
    }


def _backtest_bars(args: argparse.Namespace) -> pd.DataFrame:
    """Load explicit market inputs and align optional historical depth evidence."""
    df_bars, _ = _load_bars(args)

    book_path = getattr(args, "book_path", None)
    if book_path and Path(book_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

        df_book = load_l2_jsonl(book_path)
        df_bars = align_orderbook_to_ohlcv(df_bars, df_book)

    return df_bars
