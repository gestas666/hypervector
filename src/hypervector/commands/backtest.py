"""Backtest command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import pandas as pd
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import (
    StrategySpec,
    get_strategy,
    normalize_direction,
)
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.sizing import RiskConfig, validate_leverage
from hypervector.commands.common import (
    CommandRefused,
    _load_bars,
    align_book,
    bars_window,
    book_path_or_refuse,
    cache_age_options,
    exit_config_from_args,
)


def cmd_backtest(args: argparse.Namespace) -> int:
    """Backtest one registered strategy with leverage, fee and exit models.

    The strategy, the leverage (against the symbol's venue cap), the book path
    and the cache options are checked before any data load; a refusal exits 2.
    """
    from hypervector.sweep.metrics import compute_trial_metrics

    spec = _validated_strategy(args)
    leverage = _validated_leverage(args)
    df_bars, provenance = _backtest_bars(args)

    params = {}
    if getattr(args, "book_gate", False):
        params["book_gate"] = True
        params["max_spread_bps"] = getattr(args, "max_spread_bps", 3.0)
        params["min_obi"] = getattr(args, "min_obi", 0.1)

    entries, exits, direction = spec.build_signals(df_bars, **params)
    close = df_bars["close"].astype(float)

    exit_cfg = exit_config_from_args(args)
    risk_cfg = RiskConfig(max_size_frac=leverage)
    cost = resolve_cost_model(args.fee_model)

    m = compute_trial_metrics(
        close,
        entries,
        exits,
        direction=normalize_direction(direction),
        init_cash=args.initial_cash,
        df=df_bars,
        cost=cost,
        exit_cfg=exit_cfg,
        risk_cfg=risk_cfg,
        symbol=args.symbol,
    )

    out = _backtest_report(args, m)
    out["data_provenance"] = provenance
    out["data_window"] = bars_window(df_bars)
    print(json.dumps(out, indent=2, default=str))
    return 0


def _rounded(value: object, digits: int) -> object:
    return round(value, digits) if isinstance(value, (int, float)) else value


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
        "initial_cash": args.initial_cash,
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
            "liquidations": m.get("liquidations"),
            "min_equity": _rounded(m.get("min_equity"), 2),
            "equity_depleted": m.get("equity_depleted"),
            "effective_risk_pct": m.get("effective_risk_pct"),
            "size_cap_bound_fraction": m.get("size_cap_bound_fraction"),
        },
        "model": {
            "bar_freq": m.get("bar_freq"),
            "stop_fill_model": m.get("stop_fill_model"),
            "leverage_model": m.get("leverage_model"),
            "venue_leverage_cap": m.get("venue_leverage_cap"),
            "maintenance_margin_rate": m.get("maintenance_margin_rate"),
        },
    }


def _validated_strategy(args: argparse.Namespace) -> StrategySpec:
    """Refuse an unknown strategy or a missing book file before any data load."""
    register_all_strategies()
    try:
        spec = get_strategy(args.strategy)
    except KeyError as exc:
        raise CommandRefused(f"unknown strategy: {args.strategy}") from exc
    book_path_or_refuse(args)
    cache_age_options(args)
    return spec


def _validated_leverage(args: argparse.Namespace) -> float:
    """Leverage must be finite, positive and within the symbol's venue cap."""
    try:
        return validate_leverage(args.leverage, symbol=args.symbol)
    except ValueError as exc:
        raise CommandRefused(f"--leverage refused: {exc}") from exc


def _backtest_bars(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load explicit market inputs and align optional historical depth evidence."""
    df_bars, provenance = _load_bars(args)
    book_path = book_path_or_refuse(args)
    if book_path is not None:
        df_bars = align_book(df_bars, book_path, str(args.symbol))
    return df_bars, provenance
