"""Raise venue stops to break-even for lifecycles whose v2 profit floor has armed."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
import math

from hypervector.live.cohort_adaptive_exit_controller import lifecycle_risk_bps
from hypervector.live.cohort_adaptive_exit_policy import (
    BOOK_MAX_AGE_MS,
    BREAKEVEN_BPS,
    FLOOR_R,
)
from hypervector.live.cohort_breakeven_events import (
    BREAKEVEN_ATTEMPT_EVENT,
    BREAKEVEN_SKIPPED_EVENT as BREAKEVEN_SKIPPED_EVENT,
    RAISE_EXHAUSTED_EVENT as RAISE_EXHAUSTED_EVENT,
)
from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.hyperliquid_protocol import (
    SolBookSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.multi_asset_live_runner_support import entry_provider_strategy_id

MAX_RAISE_ATTEMPTS = 3
# Consecutive guarded skips after which an unraised floor target is surfaced. The
# software floor keeps exiting on completed-minute closes, so without this a raise
# that no fresh quote ever admits would leave the initial stop on the venue silently.
MAX_CONSECUTIVE_SKIPS = MAX_RAISE_ATTEMPTS

SkipStreaks = MutableMapping[tuple[str, int], tuple[str, int]]


def breakeven_trigger_price(entry_price: float, position_size_signed: float) -> float:
    """Return the trigger just beyond entry on the favorable side, covering round-trip costs."""
    if entry_price <= 0.0 or position_size_signed == 0.0:
        raise ValueError(
            "break-even trigger requires a positive entry and open exposure"
        )
    sign = 1.0 if position_size_signed > 0.0 else -1.0
    return entry_price * (1.0 + sign * BREAKEVEN_BPS / 10_000.0)


def breakeven_target_price(
    plan: BoundExecutionPlan | None,
    entry_price: float,
    position_size_signed: float,
) -> float:
    """Return the configured raise target: entry +/- 25 bps, or at least the 0.5R floor."""
    offset = breakeven_trigger_price(entry_price, position_size_signed)
    if plan is None or plan.breakeven_stop_target == "entry_offset":
        return offset
    long = position_size_signed > 0.0
    risk = lifecycle_risk_bps(plan, entry_price, "long" if long else "short")
    sign = 1.0 if long else -1.0
    floor = entry_price * (1.0 + sign * FLOOR_R * risk / 10_000.0)
    return max(offset, floor) if long else min(offset, floor)


def executable_exit_price(
    book: SolBookSnapshot | None, position_size_signed: float, observed_ms: int | None
) -> float | None:
    """Return the fresh top-of-book price a reduce-only exit would trade at, if known."""
    if book is None or observed_ms is None or not book.bids or not book.asks:
        return None
    if not 0 <= observed_ms - book.exchange_timestamp_ms <= BOOK_MAX_AGE_MS:
        return None
    bid, ask = book.bids[0].price, book.asks[0].price
    if not all(math.isfinite(price) and price > 0.0 for price in (bid, ask)):
        return None
    if bid >= ask:
        return None
    return bid if position_size_signed > 0.0 else ask


def raise_breakeven_stops(
    *,
    requests: frozenset[str],
    closed_symbols: set[str],
    symbols: tuple[str, ...],
    venues: Mapping[str, SolReconciliationSnapshot],
    raise_stop: Callable[[str, float], bool],
    attempts: MutableMapping[tuple[str, int], int],
    lifecycle_oids: Mapping[str, int | None],
    emit: Callable[[str, Mapping[str, object]], None],
    plans: Mapping[str, BoundExecutionPlan | None] | None = None,
    books: Mapping[str, SolBookSnapshot | None] | None = None,
    observed_ms: int | None = None,
    stop_oids: Mapping[str, int | None] | None = None,
    skips: SkipStreaks | None = None,
) -> bool:
    """Attempt each requested raise at most MAX_RAISE_ATTEMPTS times per lifecycle.

    A floor-target raise is only sent while it rests strictly on the protective
    side of the fresh executable quote; otherwise that cycle is skipped without
    spending an attempt, and the software floor still exits. A skip is journaled
    when its reason differs from the lifecycle's previous consecutive skip, and
    MAX_CONSECUTIVE_SKIPS consecutive skips are journaled once as an exhausted
    raise carrying the skip reason as its cause. ``skips`` holds each lifecycle's
    (last reason, consecutive count) across polls; a sent raise resets it.
    The adapter's nearest-tick wire rounding is monotone and venue quotes sit on
    the tick grid, so a target strictly inside the quote can round at most onto
    it, never through it. Running out of attempts is journaled once, unless the
    owned venue stop already rests at the target (a restart after a raise).
    """
    streaks: SkipStreaks = {} if skips is None else skips
    mutated = False
    for symbol in symbols:
        if symbol not in requests or symbol in closed_symbols:
            continue
        entry_oid = lifecycle_oids.get(symbol)
        venue = venues.get(symbol)
        if entry_oid is None or venue is None or venue.position.entry_price is None:
            continue
        key = (symbol, entry_oid)
        if attempts.get(key, 0) >= MAX_RAISE_ATTEMPTS:
            continue
        plan = None if plans is None else plans.get(symbol)
        size = venue.position.size_signed
        trigger = breakeven_target_price(plan, venue.position.entry_price, size)
        floor_target = plan is not None and plan.breakeven_stop_target == "floor"
        guard: dict[str, object] = {}
        if floor_target:
            quote = executable_exit_price(
                None if books is None else books.get(symbol), size, observed_ms
            )
            skipped = _skip_reason(trigger, quote, size)
            if skipped is not None:
                previous, cycles = streaks.get(key, (None, 0))
                cycles += 1
                streaks[key] = (skipped, cycles)
                if skipped != previous:
                    emit(
                        BREAKEVEN_SKIPPED_EVENT,
                        {
                            "symbol": symbol,
                            "entry_oid": entry_oid,
                            "reason": skipped,
                            "trigger_price": trigger,
                            "executable_price": quote,
                            "breakeven_stop_target": "floor",
                        },
                    )
                if cycles == MAX_CONSECUTIVE_SKIPS and not _stop_rests_at_target(
                    venue,
                    None if stop_oids is None else stop_oids.get(symbol),
                    trigger,
                    size,
                ):
                    emit(
                        RAISE_EXHAUSTED_EVENT,
                        {
                            **_exhausted_payload(
                                symbol, entry_oid, plan, trigger, attempts.get(key, 0)
                            ),
                            "cause": skipped,
                            "skipped_cycles": cycles,
                            "executable_price": quote,
                        },
                    )
                continue
            streaks.pop(key, None)
            guard = {"breakeven_stop_target": "floor", "executable_price": quote}
        attempts[key] = attempts.get(key, 0) + 1
        raised = raise_stop(symbol, trigger)
        emit(
            BREAKEVEN_ATTEMPT_EVENT,
            {
                "symbol": symbol,
                "entry_oid": entry_oid,
                "attempt": attempts[key],
                "trigger_price": trigger,
                "raised": raised,
                **guard,
            },
        )
        if raised:
            attempts[key] = MAX_RAISE_ATTEMPTS
            mutated = True
        elif attempts[key] >= MAX_RAISE_ATTEMPTS and not _stop_rests_at_target(
            venue, None if stop_oids is None else stop_oids.get(symbol), trigger, size
        ):
            emit(
                RAISE_EXHAUSTED_EVENT,
                _exhausted_payload(symbol, entry_oid, plan, trigger, attempts[key]),
            )
    return mutated


def _stop_rests_at_target(
    venue: SolReconciliationSnapshot, stop_oid: int | None, target: float, size: float
) -> bool:
    if stop_oid is None:
        return False
    current = next(
        (order.trigger_price for order in venue.open_orders if order.oid == stop_oid),
        None,
    )
    if current is None:
        return False
    return current >= target if size > 0.0 else current <= target


def _exhausted_payload(
    symbol: str,
    entry_oid: int,
    plan: BoundExecutionPlan | None,
    trigger: float,
    attempts: int,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "strategy_id": (
            None if plan is None else entry_provider_strategy_id(plan.strategy_id)
        ),
        "entry_oid": entry_oid,
        "reason": RAISE_EXHAUSTED_EVENT,
        "attempts": attempts,
        "trigger_price": trigger,
        "breakeven_stop_target": (
            "entry_offset" if plan is None else plan.breakeven_stop_target
        ),
    }


def _skip_reason(trigger: float, quote: float | None, size: float) -> str | None:
    if quote is None:
        return "executable_quote_unavailable"
    protective = trigger < quote if size > 0.0 else trigger > quote
    return None if protective else "target_not_protective_of_market"
