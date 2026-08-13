"""Sampled mark-to-market drawdown for completed event-replay trades."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from hypervector.research.mark_stop_trigger import SampledMarkSeries
from hypervector.research.range_onset_event_models import (
    EventFunding,
    EventReplayReport,
    EventReplayTrade,
)


def with_mark_to_market_drawdown(
    report: EventReplayReport,
    funding: Sequence[EventFunding],
    marks: SampledMarkSeries,
) -> EventReplayReport:
    """Attach path-dependent sampled-mark drawdown without hiding realized DD."""
    if report.status != "complete":
        return report
    peak = report.initial_equity
    maximum_drawdown = 0.0
    unobserved = 0
    for trade in report.trades:
        peak, maximum_drawdown, observed = _trade_path_drawdown(
            trade, funding, marks, peak, maximum_drawdown
        )
        unobserved += int(not observed)
    return replace(
        report,
        mark_to_market_maximum_drawdown_pct=maximum_drawdown,
        mark_to_market_unobserved_trades=unobserved,
    )


def _trade_path_drawdown(
    trade: EventReplayTrade,
    funding: Sequence[EventFunding],
    marks: SampledMarkSeries,
    peak: float,
    maximum_drawdown: float,
) -> tuple[float, float, bool]:
    entry_equity = trade.equity_before_usd - trade.entry_fee_usd
    peak, maximum_drawdown = _update(peak, maximum_drawdown, entry_equity)
    observations = marks.observations(
        trade.entry_snapshot_time_ms, trade.exit_snapshot_time_ms
    )
    funding_cash = 0.0
    funding_index = 0
    settlements = _trade_funding(trade, funding)
    for observation in observations:
        while (
            funding_index < len(settlements)
            and settlements[funding_index].timestamp_ms <= observation.timestamp_ms
        ):
            funding_cash += _funding_cashflow(trade, settlements[funding_index])
            funding_index += 1
        equity = _marked_equity(trade, observation.mark_price, funding_cash)
        peak, maximum_drawdown = _update(peak, maximum_drawdown, equity)
    peak, maximum_drawdown = _update(peak, maximum_drawdown, trade.equity_after_usd)
    return peak, maximum_drawdown, bool(observations)


def _trade_funding(
    trade: EventReplayTrade,
    funding: Sequence[EventFunding],
) -> tuple[EventFunding, ...]:
    return tuple(
        event
        for event in funding
        if trade.entry_snapshot_time_ms
        <= event.timestamp_ms
        < trade.exit_snapshot_time_ms
    )


def _funding_cashflow(trade: EventReplayTrade, event: EventFunding) -> float:
    sign = 1.0 if trade.direction == "long" else -1.0
    return -sign * trade.quantity * event.reference_price * event.rate


def _marked_equity(
    trade: EventReplayTrade,
    mark_price: float,
    funding_cash: float,
) -> float:
    sign = 1.0 if trade.direction == "long" else -1.0
    unrealized = sign * trade.quantity * (mark_price - trade.entry_price)
    return trade.equity_before_usd - trade.entry_fee_usd + funding_cash + unrealized


def _update(
    peak: float,
    maximum_drawdown: float,
    equity: float,
) -> tuple[float, float]:
    updated_peak = max(peak, equity)
    drawdown = 100.0 * (equity - updated_peak) / updated_peak
    return updated_peak, min(maximum_drawdown, drawdown)
