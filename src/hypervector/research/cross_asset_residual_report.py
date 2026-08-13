"""Aggregate immutable pair reports from residual trade lifecycles."""

from __future__ import annotations

import math

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualPairReport,
    ResidualTrade,
)


def build_residual_pair_report(
    *,
    pair: tuple[str, str],
    signal_count: int,
    equity: float,
    maximum_drawdown_pct: float,
    conflict_rejections: int,
    trades: tuple[ResidualTrade, ...],
    config: CrossAssetResidualConfig,
) -> ResidualPairReport:
    """Derive one complete aggregate report from its immutable trade rows."""
    net = [trade.net_pnl_usd for trade in trades]
    gains = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value < 0.0)
    profit_factor = (
        gains / losses if losses > 0.0 else (math.inf if gains > 0.0 else None)
    )
    return ResidualPairReport(
        left_symbol=pair[0],
        right_symbol=pair[1],
        signal_count=signal_count,
        completed_trades=len(net),
        wins=sum(value > 0.0 for value in net),
        losses=sum(value <= 0.0 for value in net),
        initial_equity=config.initial_equity,
        final_equity=equity,
        gross_pnl_usd=sum(trade.gross_pnl_usd for trade in trades),
        fees_usd=sum(trade.fees_usd for trade in trades),
        funding_cashflow_usd=sum(trade.funding_cashflow_usd for trade in trades),
        liquidation_penalties_usd=sum(
            trade.liquidation_penalty_usd for trade in trades
        ),
        net_pnl_usd=equity - config.initial_equity,
        profit_factor=profit_factor,
        maximum_drawdown_pct=maximum_drawdown_pct,
        liquidations=sum(trade.exit_reason == "liquidation" for trade in trades),
        conflict_rejections=conflict_rejections,
        trades=trades,
        limitations=(
            "fixed adverse slippage does not reconstruct historical queue position",
            "pair exits are atomic in the model but venue legs can fill asynchronously",
            "error-correction t-statistic is a diagnostic proxy, not an ADF p-value",
        ),
    )
