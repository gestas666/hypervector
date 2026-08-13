"""Multi-Strategy Long/Short Portfolio Allocator & Risk Guard.

Combines Long (uptrend) and Short (downtrend) signals into a unified portfolio
with conflict resolution, regime scaling, and cost-aware equity tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from hypervector.regime.adaptive import detect_4state_regime
from hypervector.strategies.registry import get_strategy
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics


@dataclass
class PortfolioResult:
    long_strategy: str
    short_strategy: str
    symbol: str
    timeframe: str
    combined_metrics: dict[str, Any]
    long_metrics: dict[str, Any]
    short_metrics: dict[str, Any]


def run_long_short_portfolio(
    df: pd.DataFrame,
    *,
    long_strategy_name: str = "pine_composite_long",
    short_strategy_name: str = "pine_composite_short",
    long_params: dict[str, Any] | None = None,
    short_params: dict[str, Any] | None = None,
    cost_preset: str = "hl_taker_default",
    exit_cfg: ExitConfig | None = None,
    init_cash: float = 10_000.0,
    composition_mode: bool = False,
) -> PortfolioResult:
    """Run dual-track Long/Short strategy backtest with optional regime-aware portfolio allocation."""
    from hypervector.strategies import register_all_strategies

    register_all_strategies()
    long_spec = get_strategy(long_strategy_name)
    short_spec = get_strategy(short_strategy_name)
    cost = resolve_cost_model(cost_preset)
    exit_cfg = exit_cfg or ExitConfig(mode="atr")

    l_params = long_params or {}
    s_params = short_params or {}

    # Build raw signals
    entries_l, exits_l, _ = long_spec.build_signals(df, **l_params)
    entries_s, exits_s, _ = short_spec.build_signals(df, **s_params)

    if composition_mode:
        # Detect 4-State Regime for composition arm
        regime = detect_4state_regime(df)
        entries_l_final = entries_l & (regime != "BEAR_TREND")
        entries_s_final = entries_s & (regime != "BULL_TREND")
        conflict = entries_l_final & entries_s_final
        entries_s_final = entries_s_final & (~conflict)
    else:
        # Raw ungated strategy signals by default (SRS_HV1_REGIME_NO_GATE)
        # Enforce perpetual venue single position rule: resolve simultaneous Long/Short conflicts
        conflict = entries_l & entries_s
        entries_l_final = entries_l
        entries_s_final = entries_s & (~conflict)

    close = df["close"].astype(float)

    # Metrics computation
    m_long = compute_trial_metrics(
        close,
        entries_l_final,
        exits_l,
        direction="long",
        init_cash=init_cash,
        df=df,
        cost=cost,
        exit_cfg=exit_cfg,
    )
    m_short = compute_trial_metrics(
        close,
        entries_s_final,
        exits_s,
        direction="short",
        init_cash=init_cash,
        df=df,
        cost=cost,
        exit_cfg=exit_cfg,
    )

    # Combined Portfolio metrics
    net_pnl_comb = float(m_long.get("net_pnl", 0.0)) + float(
        m_short.get("net_pnl", 0.0)
    )
    trades_comb = int(m_long.get("trade_count", 0)) + int(m_short.get("trade_count", 0))
    wins_comb = int(m_long.get("wins", 0)) + int(m_short.get("wins", 0))
    win_pct_comb = (wins_comb / trades_comb * 100.0) if trades_comb > 0 else 0.0

    sh_l = float(m_long.get("sharpe", 0.0))
    sh_s = float(m_short.get("sharpe", 0.0))
    sharpe_comb = (sh_l + sh_s) / 2.0

    combined_metrics = {
        "net_pnl": net_pnl_comb,
        "total_return_pct": (net_pnl_comb / init_cash) * 100.0,
        "sharpe": sharpe_comb,
        "trade_count": trades_comb,
        "trades": trades_comb,
        "wins": wins_comb,
        "win_pct": win_pct_comb,
        "long_net_pnl": float(m_long.get("net_pnl", 0.0)),
        "short_net_pnl": float(m_short.get("net_pnl", 0.0)),
    }

    symbol = str(df.attrs.get("symbol", "BTC"))
    timeframe = str(df.attrs.get("timeframe", "1m"))

    return PortfolioResult(
        long_strategy=long_strategy_name,
        short_strategy=short_strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        combined_metrics=combined_metrics,
        long_metrics=m_long,
        short_metrics=m_short,
    )
