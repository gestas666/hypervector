"""Aggregate accounting for Market Cipher shared-portfolio replay."""

from __future__ import annotations

from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayReport,
    MarketCipherReplayTrade,
    ReplayRejection,
)


def build_market_cipher_replay_report(
    *,
    initial_equity: float,
    final_equity: float,
    maximum_drawdown_pct: float,
    maximum_concurrent_positions: int,
    trades: list[MarketCipherReplayTrade],
    rejections: list[ReplayRejection],
) -> MarketCipherReplayReport:
    """Reconcile every completed trade into one immutable report."""
    gross = sum(trade.gross_pnl_usd for trade in trades)
    fees = sum(trade.fees_usd for trade in trades)
    funding = sum(trade.funding_cashflow_usd for trade in trades)
    penalties = sum(trade.liquidation_penalty_usd for trade in trades)
    net = gross - fees + funding - penalties
    expected_equity = initial_equity + net
    if abs(expected_equity - final_equity) > 1e-7:
        raise RuntimeError(
            "Market Cipher replay accounting failed: "
            f"expected={expected_equity} actual={final_equity}"
        )
    profits = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    profit_factor = profits / losses if losses > 0.0 else None
    return MarketCipherReplayReport(
        initial_equity=initial_equity,
        final_equity=final_equity,
        gross_pnl_usd=gross,
        total_fees_usd=fees,
        funding_cashflow_usd=funding,
        liquidation_penalties_usd=penalties,
        net_pnl_usd=net,
        completed_trades=len(trades),
        wins=sum(trade.net_pnl_usd > 0.0 for trade in trades),
        losses=sum(trade.net_pnl_usd < 0.0 for trade in trades),
        profit_factor=profit_factor,
        maximum_drawdown_pct=maximum_drawdown_pct,
        liquidations=sum(trade.exit_reason == "liquidation" for trade in trades),
        maximum_concurrent_positions=maximum_concurrent_positions,
        trades=tuple(trades),
        rejections=tuple(rejections),
        limitations=(
            "OHLC bars cannot identify intrabar path or queue position",
            "liquidation-before-stop-before-target ordering is pessimistic",
            "configured slippage and liquidation penalty are stress assumptions",
        ),
    )
