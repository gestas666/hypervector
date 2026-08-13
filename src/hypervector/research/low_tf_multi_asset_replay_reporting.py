"""Aggregate reporting for low-timeframe one-minute-path replay."""

from __future__ import annotations

from collections.abc import Sequence

from hypervector.research.low_tf_multi_asset_replay_models import (
    LowTfReplayRejection,
    LowTfReplayReport,
    LowTfReplayTrade,
)


def build_low_tf_replay_report(
    *,
    initial_equity: float,
    final_equity: float,
    maximum_drawdown_pct: float,
    trades: Sequence[LowTfReplayTrade],
    rejections: Sequence[LowTfReplayRejection],
) -> LowTfReplayReport:
    """Aggregate immutable trade and rejection records for one strategy cell."""
    gross = sum(trade.gross_pnl_usd for trade in trades)
    fees = sum(trade.fees_usd for trade in trades)
    funding = sum(trade.funding_cashflow_usd for trade in trades)
    penalties = sum(trade.liquidation_penalty_usd for trade in trades)
    profits = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return LowTfReplayReport(
        initial_equity,
        final_equity,
        gross,
        fees,
        funding,
        penalties,
        final_equity - initial_equity,
        len(trades),
        sum(trade.net_pnl_usd > 0.0 for trade in trades),
        sum(trade.net_pnl_usd <= 0.0 for trade in trades),
        profits / losses if losses > 0.0 else None,
        maximum_drawdown_pct,
        sum(trade.exit_reason == "liquidation" for trade in trades),
        sum(trade.same_minute_ambiguous for trade in trades),
        tuple(trades),
        tuple(rejections),
        ("one-minute OHLC cannot order multiple crossings inside one minute",),
    )
