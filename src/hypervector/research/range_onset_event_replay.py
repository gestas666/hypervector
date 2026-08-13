"""Chronological taker event replay for the SOL range-onset challenger."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from hypervector.research.market_depth_database import TimedMarketDepthFill
from hypervector.research.market_depth_fill import MarketSide
from hypervector.research.range_onset_event_models import (
    EventExitReason,
    EventFunding,
    EventReplayConfig,
    EventReplayReport,
    EventReplayTrade,
    EventSignal,
    ReplayStatus,
)
from hypervector.research.range_onset_event_barriers import first_barrier_crossing
from hypervector.research.range_onset_event_risk import (
    BarrierCrossing,
    EventRiskPosition,
    funding_cashflow,
    liquidation_price,
)
from hypervector.research.shared_portfolio_models import Direction

MarketFill = Callable[[int, MarketSide, float], TimedMarketDepthFill]
StopCrossing = BarrierCrossing
_END_OFFSET_MS = 1


@dataclass
class _OpenPosition:
    direction: Direction
    entry_event: EventSignal
    entry_fill: TimedMarketDepthFill
    quantity: float
    stop_price: float
    isolated_margin: float
    equity_before: float
    entry_fee: float


@dataclass
class _State:
    equity: float
    peak_equity: float
    drawdown_pct: float = 0.0
    conflicts: int = 0
    trades: list[EventReplayTrade] = field(default_factory=list)


@dataclass(frozen=True)
class _PlannedExit:
    decision_time_ms: int
    event_time_ms: int
    reason: EventExitReason
    signal_index: int | None
    reversal: EventSignal | None


class _DepthFailure(RuntimeError):
    pass


def replay_range_onset_events(
    events: Sequence[EventSignal],
    funding: Sequence[EventFunding],
    config: EventReplayConfig,
    *,
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    end_time_ms: int,
) -> EventReplayReport:
    """Replay one position at a time using causal triggers and visible depth."""
    _validate_replay_inputs(events, funding, end_time_ms)
    state = _State(config.initial_equity, config.initial_equity)
    try:
        _replay_loop(
            events, funding, state, config, market_fill, stop_crossing, end_time_ms
        )
    except _DepthFailure as exc:
        return _report("depth_failure", state, config, str(exc))
    except LookupError as exc:
        return _report("evidence_failure", state, config, str(exc))
    return _report("complete", state, config, None)


def _replay_loop(
    events: Sequence[EventSignal],
    funding: Sequence[EventFunding],
    state: _State,
    config: EventReplayConfig,
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    end_time_ms: int,
) -> None:
    index = 0
    while index < len(events):
        entry_index = _next_entry_index(events, index, state)
        if entry_index is None:
            return
        opened = _open_position(events[entry_index], state, config, market_fill)
        index = _replay_lifecycle(
            events,
            funding,
            entry_index + 1,
            opened,
            state,
            config,
            market_fill,
            stop_crossing,
            end_time_ms,
        )


def _replay_lifecycle(
    events: Sequence[EventSignal],
    funding: Sequence[EventFunding],
    index: int,
    opened: _OpenPosition,
    state: _State,
    config: EventReplayConfig,
    market_fill: MarketFill,
    stop_crossing: StopCrossing,
    end_time_ms: int,
) -> int:
    while True:
        planned = _planned_exit(events, index, opened, config, end_time_ms)
        crossing = first_barrier_crossing(
            _risk_position(opened),
            funding,
            config,
            stop_crossing,
            planned.event_time_ms,
        )
        if crossing is not None:
            _close_position(
                opened,
                crossing.event_time_ms,
                crossing.event_time_ms,
                crossing.reason,
                state,
                funding,
                config,
                market_fill,
            )
            return _first_event_after(
                events,
                index,
                crossing.event_time_ms + config.reentry_cooldown_ms,
            )
        _close_position(
            opened,
            planned.decision_time_ms,
            planned.event_time_ms,
            planned.reason,
            state,
            funding,
            config,
            market_fill,
        )
        index = _next_index(events, index, planned, config)
        reversal = _open_reversal(planned.reversal, state, config, market_fill)
        if reversal is None:
            return index
        opened = reversal


def _next_entry_index(
    events: Sequence[EventSignal],
    start: int,
    state: _State,
) -> int | None:
    for index in range(start, len(events)):
        direction, conflict = _desired_entry(events[index])
        state.conflicts += int(conflict)
        if direction is not None:
            return index
    return None


def _open_position(
    event: EventSignal,
    state: _State,
    config: EventReplayConfig,
    market_fill: MarketFill,
) -> _OpenPosition:
    direction, conflict = _desired_entry(event)
    if conflict or direction is None:
        raise RuntimeError("entry event must contain one unambiguous direction")
    side: MarketSide = "buy" if direction == "long" else "sell"
    equity_before = state.equity
    notional = equity_before * config.margin_fraction * config.leverage
    quantity = notional / event.reference_price
    fill = market_fill(_submission_time(event, config), side, quantity)
    _require_complete(fill, "entry")
    entry_fee = quantity * fill.fill.vwap * config.taker_fee_rate
    isolated_margin = equity_before * config.margin_fraction
    state.equity -= entry_fee
    _update_drawdown(state)
    stop = _stop_price(direction, fill.fill.vwap, config.stop_bps)
    return _OpenPosition(
        direction,
        event,
        fill,
        quantity,
        stop,
        isolated_margin,
        equity_before,
        entry_fee,
    )


def _risk_position(opened: _OpenPosition) -> EventRiskPosition:
    return EventRiskPosition(
        opened.direction,
        opened.quantity,
        opened.entry_fill.fill.vwap,
        opened.isolated_margin,
        opened.entry_fee,
        opened.entry_fill.snapshot_time_ms,
        opened.stop_price,
    )


def _planned_exit(
    events: Sequence[EventSignal],
    start: int,
    opened: _OpenPosition,
    config: EventReplayConfig,
    end_time_ms: int,
) -> _PlannedExit:
    deadline = opened.entry_fill.snapshot_time_ms + config.max_hold_ms
    for index in range(start, len(events)):
        event = events[index]
        submission_time_ms = _submission_time(event, config)
        if submission_time_ms > deadline:
            break
        reason = _signal_exit_reason(event, opened.direction)
        if reason is not None:
            reversal = event if _is_opposite_entry(event, opened.direction) else None
            return _PlannedExit(
                event.decision_time_ms,
                submission_time_ms,
                reason,
                index,
                reversal,
            )
    if deadline < end_time_ms:
        return _PlannedExit(deadline, deadline, "max_hold", None, None)
    end_event_ms = end_time_ms - _END_OFFSET_MS
    return _PlannedExit(end_event_ms, end_event_ms, "end_of_data", None, None)


def _close_position(
    opened: _OpenPosition,
    decision_time_ms: int,
    submission_time_ms: int,
    reason: EventExitReason,
    state: _State,
    funding: Sequence[EventFunding],
    config: EventReplayConfig,
    market_fill: MarketFill,
) -> None:
    side: MarketSide = "sell" if opened.direction == "long" else "buy"
    fill = market_fill(submission_time_ms, side, opened.quantity)
    _require_complete(fill, "exit")
    funding_cash = _funding_cashflow(opened, fill.snapshot_time_ms, funding)
    trade = _trade(
        opened,
        fill,
        decision_time_ms,
        reason,
        funding_cash,
        state,
        config,
    )
    state.equity = trade.equity_after_usd
    state.trades.append(trade)
    _update_drawdown(state)


def _trade(
    opened: _OpenPosition,
    exit_fill: TimedMarketDepthFill,
    exit_event_ms: int,
    reason: EventExitReason,
    funding_cash: float,
    state: _State,
    config: EventReplayConfig,
) -> EventReplayTrade:
    sign = 1.0 if opened.direction == "long" else -1.0
    entry_price, exit_price = opened.entry_fill.fill.vwap, exit_fill.fill.vwap
    gross = sign * opened.quantity * (exit_price - entry_price)
    exit_fee = opened.quantity * exit_price * config.taker_fee_rate
    fees = opened.entry_fee + exit_fee
    net = gross - fees + funding_cash
    liquidation = liquidation_price(_risk_position(opened), config, funding_cash)
    return EventReplayTrade(
        opened.direction,
        opened.entry_event.decision_time_ms,
        opened.entry_fill.snapshot_time_ms,
        exit_event_ms,
        exit_fill.snapshot_time_ms,
        entry_price,
        exit_price,
        opened.quantity,
        opened.stop_price,
        liquidation,
        opened.isolated_margin,
        opened.entry_fill.fill.impact_bps,
        exit_fill.fill.impact_bps,
        opened.entry_fill.snapshot_time_ms - opened.entry_event.decision_time_ms,
        exit_fill.snapshot_time_ms - exit_event_ms,
        gross,
        opened.entry_fee,
        exit_fee,
        fees,
        funding_cash,
        net,
        opened.equity_before,
        state.equity + gross - exit_fee + funding_cash,
        reason,
    )


def _funding_cashflow(
    opened: _OpenPosition,
    exit_time_ms: int,
    funding: Sequence[EventFunding],
) -> float:
    return sum(
        funding_cashflow(_risk_position(opened), event)
        for event in funding
        if opened.entry_fill.snapshot_time_ms <= event.timestamp_ms < exit_time_ms
    )


def _report(
    status: ReplayStatus,
    state: _State,
    config: EventReplayConfig,
    failure: str | None,
) -> EventReplayReport:
    profits = sum(max(trade.net_pnl_usd, 0.0) for trade in state.trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in state.trades)
    return EventReplayReport(
        status,
        config.initial_equity,
        state.equity,
        len(state.trades),
        sum(trade.net_pnl_usd > 0.0 for trade in state.trades),
        sum(trade.net_pnl_usd <= 0.0 for trade in state.trades),
        sum(trade.exit_reason == "liquidation" for trade in state.trades),
        profits / losses if losses > 0.0 else None,
        state.drawdown_pct,
        None,
        None,
        sum(trade.fees_usd for trade in state.trades),
        sum(trade.funding_cashflow_usd for trade in state.trades),
        state.conflicts,
        failure,
        tuple(state.trades),
    )


def _desired_entry(event: EventSignal) -> tuple[Direction | None, bool]:
    if event.long_entry and event.short_entry:
        return None, True
    if event.long_entry:
        return "long", False
    if event.short_entry:
        return "short", False
    return None, False


def _signal_exit_reason(
    event: EventSignal,
    direction: Direction,
) -> EventExitReason | None:
    if _is_opposite_entry(event, direction):
        return "opposite_signal"
    if (direction == "long" and event.long_exit) or (
        direction == "short" and event.short_exit
    ):
        return "signal"
    return None


def _is_opposite_entry(event: EventSignal, direction: Direction) -> bool:
    desired, conflict = _desired_entry(event)
    return not conflict and desired is not None and desired != direction


def _open_reversal(
    event: EventSignal | None,
    state: _State,
    config: EventReplayConfig,
    market_fill: MarketFill,
) -> _OpenPosition | None:
    if event is None:
        return None
    return _open_position(event, state, config, market_fill)


def _next_index(
    events: Sequence[EventSignal],
    start: int,
    planned: _PlannedExit,
    config: EventReplayConfig,
) -> int:
    if planned.signal_index is not None:
        return planned.signal_index + 1
    if planned.reason == "max_hold":
        return _first_event_after(
            events,
            start,
            planned.event_time_ms + config.reentry_cooldown_ms,
        )
    return len(events)


def _first_event_after(
    events: Sequence[EventSignal],
    start: int,
    threshold_ms: int,
) -> int:
    for index in range(start, len(events)):
        if events[index].decision_time_ms >= threshold_ms:
            return index
    return len(events)


def _stop_price(direction: Direction, entry: float, stop_bps: float) -> float:
    fraction = stop_bps / 10_000.0
    return entry * (1.0 - fraction if direction == "long" else 1.0 + fraction)


def _submission_time(event: EventSignal, config: EventReplayConfig) -> int:
    return event.decision_time_ms + config.decision_delay_ms


def _require_complete(fill: TimedMarketDepthFill, label: str) -> None:
    if not fill.fill.complete:
        raise _DepthFailure(
            f"{label} visible depth filled {fill.fill.filled_quantity:g} of "
            f"{fill.fill.requested_quantity:g}"
        )


def _update_drawdown(state: _State) -> None:
    state.peak_equity = max(state.peak_equity, state.equity)
    drawdown = 100.0 * (state.equity - state.peak_equity) / state.peak_equity
    state.drawdown_pct = min(state.drawdown_pct, drawdown)


def _validate_replay_inputs(
    events: Sequence[EventSignal],
    funding: Sequence[EventFunding],
    end_time_ms: int,
) -> None:
    _positive_integer(end_time_ms, "end_time_ms")
    event_times = [event.decision_time_ms for event in events]
    funding_times = [event.timestamp_ms for event in funding]
    if event_times != sorted(set(event_times)):
        raise ValueError("event signals must have unique increasing timestamps")
    if funding_times != sorted(set(funding_times)):
        raise ValueError("funding events must have unique increasing timestamps")
    if event_times and event_times[-1] >= end_time_ms:
        raise ValueError("event signals must precede end_time_ms")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
