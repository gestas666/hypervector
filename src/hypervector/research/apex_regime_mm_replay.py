"""Report-only event replay for the repaired Apex regime market maker."""

from __future__ import annotations

import math
from typing import Literal, Sequence

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.apex_regime_mm_policy import (
    ApexMMMarketState,
    quote_apex_regime_mm_v2,
)
from hypervector.research.apex_regime_mm_replay_types import (
    ApexMMFill,
    ApexMMReplayConfig,
    ApexMMReplayResult,
    FundingPoint,
    LiquiditySide,
    ReplayEvent,
    ReplayFill,
    ReplayOrder,
    ReplayState,
    Side,
)


_STRATEGY_ID = "apex_regime_mm_v2"


def replay_apex_regime_mm_v2(
    events: Sequence[ReplayEvent],
    funding: Sequence[FundingPoint],
    config: ApexMMReplayConfig = ApexMMReplayConfig(),
) -> ApexMMReplayResult:
    """Replay two-sided quotes through public L2 and aggressor trade events."""
    _validate_evidence(events, funding)
    state = ReplayState(
        config=config,
        cash=config.initial_equity_usd,
        peak_equity=config.initial_equity_usd,
    )
    for event in events:
        _apply_funding(state, funding, event.exchange_ts_ms)
        _advance_orders(state, event.exchange_ts_ms)
        if isinstance(event, L2SnapshotEvent):
            _on_book(state, event)
        else:
            _on_trade(state, event)
    _flatten_at_end(state, events[-1].exchange_ts_ms)
    final_equity = _marked_equity(state)
    return _result(state, final_equity)


def _validate_evidence(
    events: Sequence[ReplayEvent],
    funding: Sequence[FundingPoint],
) -> None:
    if not events:
        raise ValueError("market-maker replay requires event evidence")
    event_times = [event.exchange_ts_ms for event in events]
    if event_times != sorted(event_times):
        raise ValueError("market-maker events must be chronological")
    symbols = {event.symbol for event in events}
    if len(symbols) != 1:
        raise ValueError("market-maker replay requires one symbol")
    if not any(isinstance(event, L2SnapshotEvent) for event in events):
        raise ValueError("market-maker replay requires L2 snapshots")
    funding_times = [point.timestamp_ms for point in funding]
    if funding_times != sorted(funding_times):
        raise ValueError("funding points must be chronological")


def _on_book(state: ReplayState, book: L2SnapshotEvent) -> None:
    midpoint = (book.bids[0].price + book.asks[0].price) / 2.0
    _complete_markouts(state, book.exchange_ts_ms, midpoint)
    cascade = _cascade_side(state, midpoint)
    state.current_book = book
    _record_mid_return(state, midpoint)
    _update_risk(state, midpoint)
    if state.inventory != 0.0 and _is_liquidatable(state, midpoint):
        _liquidate(state, book)
    _update_drawdown(state, midpoint)
    if state.last_quote_ms is None or (
        book.exchange_ts_ms - state.last_quote_ms >= state.config.quote_refresh_ms
    ):
        _schedule_quotes(state, book, cascade)


def _on_trade(state: ReplayState, trade: PublicTradeEvent) -> None:
    side: Side = "sell" if trade.aggressor_side.lower() == "buy" else "buy"
    order = state.active.get(side)
    if order is None or not _order_is_active(order, trade.exchange_ts_ms):
        return
    crossed = (
        trade.price >= order.price if side == "sell" else trade.price <= order.price
    )
    if not crossed:
        return
    remaining_trade = trade.size
    depleted = min(order.queue_ahead, remaining_trade)
    order.queue_ahead -= depleted
    remaining_trade -= depleted
    state.queue_depleted += depleted
    if remaining_trade <= 0.0:
        return
    capacity = _remaining_capacity(state, side, order.price)
    fill_quantity = min(order.remaining, remaining_trade, capacity)
    if fill_quantity <= 0.0:
        return
    _apply_fill(
        state,
        trade.exchange_ts_ms,
        order.role,
        side,
        order.price,
        fill_quantity,
        "maker",
        state.config.maker_fee_rate,
    )
    order.remaining -= fill_quantity
    if order.remaining <= 1e-12:
        state.active.pop(side, None)


def _schedule_quotes(
    state: ReplayState,
    book: L2SnapshotEvent,
    cascade: Literal["none", "down", "up"],
) -> None:
    quote = quote_apex_regime_mm_v2(
        ApexMMMarketState(
            best_bid=book.bids[0].price,
            best_ask=book.asks[0].price,
            best_bid_size=book.bids[0].size,
            best_ask_size=book.asks[0].size,
            volatility_bps=_volatility_bps(state),
            inventory_qty=state.inventory,
            equity_usd=max(_marked_equity(state), 1e-9),
            book_age_ms=0,
            cascade_side=cascade,
        ),
        state.config.policy,
    )
    state.last_quote_ms = book.exchange_ts_ms
    desired = {
        "buy": (quote.bid_price, quote.bid_size, "maker_bid"),
        "sell": (quote.ask_price, quote.ask_size, "maker_ask"),
    }
    for side, (price, size, role) in desired.items():
        current = state.active.get(side)
        if current is not None:
            current.cancel_at_ms = book.exchange_ts_ms + state.config.cancel_latency_ms
        state.pending.pop(side, None)
        if not quote.active or price is None or size <= 0.0:
            continue
        delay = state.config.submit_latency_ms
        if current is not None:
            delay += state.config.cancel_latency_ms
        state.pending[side] = ReplayOrder(
            side=side,
            role=role,
            price=price,
            remaining=size,
            queue_ahead=_displayed_queue(book, side, price),
            active_at_ms=book.exchange_ts_ms + delay,
        )


def _advance_orders(state: ReplayState, timestamp_ms: int) -> None:
    for side, order in tuple(state.active.items()):
        if order.cancel_at_ms is not None and timestamp_ms >= order.cancel_at_ms:
            state.active.pop(side, None)
    for side, order in tuple(state.pending.items()):
        if timestamp_ms >= order.active_at_ms:
            state.active[side] = order
            state.pending.pop(side, None)


def _order_is_active(order: ReplayOrder, timestamp_ms: int) -> bool:
    return timestamp_ms >= order.active_at_ms and (
        order.cancel_at_ms is None or timestamp_ms < order.cancel_at_ms
    )


def _displayed_queue(book: L2SnapshotEvent, side: Side, price: float) -> float:
    levels = book.bids if side == "buy" else book.asks
    return next((level.size for level in levels if level.price == price), 0.0)


def _remaining_capacity(state: ReplayState, side: Side, price: float) -> float:
    equity = max(_marked_equity(state), 0.0)
    maximum = equity * state.config.policy.maximum_inventory_fraction / price
    if side == "buy":
        return max(0.0, maximum - state.inventory)
    return max(0.0, maximum + state.inventory)


def _apply_fill(
    state: ReplayState,
    timestamp_ms: int,
    role: str,
    side: Side,
    price: float,
    quantity: float,
    liquidity: LiquiditySide,
    fee_rate: float,
) -> None:
    fee = price * quantity * fee_rate
    old_inventory = state.inventory
    signed = quantity if side == "buy" else -quantity
    state.cash += -price * quantity - fee if side == "buy" else price * quantity - fee
    state.inventory += signed
    _update_position_basis(state, old_inventory, signed, price, fee)
    if liquidity == "maker":
        state.maker_fees += fee
    else:
        state.taker_fees += fee
    state.fills.append(
        ReplayFill(timestamp_ms, role, side, price, quantity, liquidity, fee)
    )
    mark = _current_mid(state) or price
    state.max_inventory_notional = max(
        state.max_inventory_notional,
        abs(state.inventory) * mark,
    )
    _update_drawdown(state, mark)


def _update_position_basis(
    state: ReplayState,
    old_inventory: float,
    signed_fill: float,
    price: float,
    fee: float,
) -> None:
    new_inventory = old_inventory + signed_fill
    if old_inventory == 0.0 or old_inventory * signed_fill > 0.0:
        old_notional = abs(old_inventory) * state.average_entry
        state.average_entry = (old_notional + abs(signed_fill) * price) / abs(
            new_inventory
        )
        state.position_open_fees += fee
        return
    if abs(signed_fill) < abs(old_inventory):
        retained = abs(new_inventory / old_inventory)
        state.position_open_fees *= retained
        state.position_funding *= retained
        return
    if abs(signed_fill) == abs(old_inventory):
        state.average_entry = 0.0
        state.position_open_fees = 0.0
        state.position_funding = 0.0
        return
    state.average_entry = price
    state.position_open_fees = fee * abs(new_inventory / signed_fill)
    state.position_funding = 0.0


def _apply_funding(
    state: ReplayState,
    funding: Sequence[FundingPoint],
    timestamp_ms: int,
) -> None:
    while state.next_funding_index < len(funding):
        point = funding[state.next_funding_index]
        if point.timestamp_ms > timestamp_ms:
            return
        midpoint = _current_mid(state)
        if midpoint is not None and state.inventory != 0.0:
            cashflow = -state.inventory * midpoint * point.hourly_rate
            state.cash += cashflow
            state.funding_cashflow += cashflow
            state.position_funding += cashflow
        state.next_funding_index += 1


def _liquidation_position(state: ReplayState) -> IsolatedMarginPosition:
    side = "long" if state.inventory > 0.0 else "short"
    quantity = abs(state.inventory)
    notional = quantity * state.average_entry
    return IsolatedMarginPosition(
        symbol=state.current_book.symbol if state.current_book else "BTC",
        side=side,
        quantity=quantity,
        entry_price=state.average_entry,
        isolated_margin=notional / state.config.leverage,
        maintenance_rate=maintenance_rate_for_max_leverage(
            state.config.venue_max_leverage
        ),
        fees_paid_usd=state.position_open_fees,
        funding_net_usd=state.position_funding,
    )


def _update_risk(state: ReplayState, midpoint: float) -> None:
    if state.inventory == 0.0:
        return
    liquidation_price = _liquidation_position(state).liquidation_price()
    if state.inventory > 0.0:
        distance = (midpoint - liquidation_price) / midpoint * 100.0
    else:
        distance = (liquidation_price - midpoint) / midpoint * 100.0
    bounded = max(0.0, distance)
    current = state.minimum_liquidation_distance_pct
    state.minimum_liquidation_distance_pct = (
        bounded if current is None else min(current, bounded)
    )


def _is_liquidatable(state: ReplayState, midpoint: float) -> bool:
    return _liquidation_position(state).state(midpoint).liquidatable


def _liquidate(state: ReplayState, book: L2SnapshotEvent) -> None:
    side: Side = "sell" if state.inventory > 0.0 else "buy"
    price = book.bids[0].price if side == "sell" else book.asks[0].price
    _apply_fill(
        state,
        book.exchange_ts_ms,
        "liquidation_unwind",
        side,
        price,
        abs(state.inventory),
        "taker",
        state.config.taker_fee_rate,
    )
    state.liquidations += 1
    state.active.clear()
    state.pending.clear()


def _flatten_at_end(state: ReplayState, timestamp_ms: int) -> None:
    state.active.clear()
    state.pending.clear()
    book = state.current_book
    if book is None or state.inventory == 0.0:
        return
    side: Side = "sell" if state.inventory > 0.0 else "buy"
    price = book.bids[0].price if side == "sell" else book.asks[0].price
    _apply_fill(
        state,
        timestamp_ms,
        "end_flatten",
        side,
        price,
        abs(state.inventory),
        "taker",
        state.config.taker_fee_rate,
    )


def _complete_markouts(state: ReplayState, timestamp_ms: int, midpoint: float) -> None:
    for fill in state.fills:
        if fill.markout_bps is not None:
            continue
        if timestamp_ms < fill.timestamp_ms + state.config.markout_horizon_ms:
            continue
        sign = 1.0 if fill.side == "buy" else -1.0
        fill.markout_bps = sign * (midpoint / fill.price - 1.0) * 10_000.0


def _record_mid_return(state: ReplayState, midpoint: float) -> None:
    if state.previous_mid is not None:
        state.mid_returns.append(math.log(midpoint / state.previous_mid))
    state.previous_mid = midpoint


def _volatility_bps(state: ReplayState) -> float:
    if len(state.mid_returns) < 2:
        return 0.0
    mean = sum(state.mid_returns) / len(state.mid_returns)
    variance = sum((value - mean) ** 2 for value in state.mid_returns) / len(
        state.mid_returns
    )
    return math.sqrt(variance) * 10_000.0


def _cascade_side(
    state: ReplayState,
    midpoint: float,
) -> Literal["none", "down", "up"]:
    if state.previous_mid is None:
        return "none"
    move_bps = (midpoint / state.previous_mid - 1.0) * 10_000.0
    if move_bps <= -state.config.cascade_trigger_bps:
        return "down"
    if move_bps >= state.config.cascade_trigger_bps:
        return "up"
    return "none"


def _current_mid(state: ReplayState) -> float | None:
    if state.current_book is None:
        return None
    return (state.current_book.bids[0].price + state.current_book.asks[0].price) / 2.0


def _marked_equity(state: ReplayState) -> float:
    midpoint = _current_mid(state)
    return state.cash if midpoint is None else state.cash + state.inventory * midpoint


def _update_drawdown(state: ReplayState, midpoint: float) -> None:
    equity = state.cash + state.inventory * midpoint
    state.peak_equity = max(state.peak_equity, equity)
    drawdown = (equity / state.peak_equity - 1.0) * 100.0
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)


def _result(state: ReplayState, final_equity: float) -> ApexMMReplayResult:
    fills = tuple(
        ApexMMFill(
            fill.timestamp_ms,
            _STRATEGY_ID,
            fill.order_role,
            fill.side,
            fill.price,
            fill.quantity,
            fill.liquidity_side,
            fill.fee_usd,
            fill.markout_bps,
        )
        for fill in state.fills
    )
    return ApexMMReplayResult(
        strategy_id=_STRATEGY_ID,
        execution_authority="none",
        place_attempted=False,
        initial_equity_usd=state.config.initial_equity_usd,
        final_equity_usd=final_equity,
        net_pnl_usd=final_equity - state.config.initial_equity_usd,
        maker_fees_usd=state.maker_fees,
        taker_fees_usd=state.taker_fees,
        funding_cashflow_usd=state.funding_cashflow,
        maker_fill_count=sum(fill.liquidity_side == "maker" for fill in fills),
        taker_fill_count=sum(fill.liquidity_side == "taker" for fill in fills),
        queue_depleted_quantity=state.queue_depleted,
        final_inventory_qty=state.inventory,
        maximum_inventory_notional_usd=state.max_inventory_notional,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        minimum_liquidation_distance_pct=state.minimum_liquidation_distance_pct,
        liquidations=state.liquidations,
        fills=fills,
    )
