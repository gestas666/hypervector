"""Economic summary helpers for report-only HYPE exit replays."""

from __future__ import annotations

from hypervector.research.hype_breakout_exit_models import (
    HypeExitReplayReport,
    HypeExitTrade,
)


def summarize_hype_exit_replay(
    policy_id: str,
    trades: list[HypeExitTrade],
    occupied_signals: int,
    reset_blocked_signals: int,
) -> HypeExitReplayReport:
    """Build one deterministic economic report from completed lifecycles."""
    net = [trade.net_return_bps for trade in trades]
    profits = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value <= 0.0)
    return HypeExitReplayReport(
        policy_id,
        len(trades),
        sum(value > 0.0 for value in net),
        sum(value <= 0.0 for value in net),
        sum(net),
        profits,
        losses,
        profits / losses if losses else None,
        _maximum_drawdown(net),
        sum(trade.fee_bps for trade in trades),
        sum(trade.funding_bps for trade in trades),
        occupied_signals,
        _exit_reason_counts(trades),
        _monthly_net(trades),
        tuple(trades),
        reset_blocked_signals=reset_blocked_signals,
    )


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _exit_reason_counts(trades: list[HypeExitTrade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in trades:
        counts[trade.exit_reason] = counts.get(trade.exit_reason, 0) + 1
    return counts


def _monthly_net(trades: list[HypeExitTrade]) -> dict[str, float]:
    values: dict[str, float] = {}
    for trade in trades:
        month = trade.exit_time_utc[:7]
        values[month] = values.get(month, 0.0) + trade.net_return_bps
    return values
