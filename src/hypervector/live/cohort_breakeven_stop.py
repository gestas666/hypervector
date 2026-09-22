"""Raise venue stops to break-even for lifecycles whose v2 profit floor has armed."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping

from hypervector.live.cohort_adaptive_exit_policy import BREAKEVEN_BPS
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot

MAX_RAISE_ATTEMPTS = 3


def breakeven_trigger_price(entry_price: float, position_size_signed: float) -> float:
    """Return the trigger just beyond entry on the favorable side, covering round-trip costs."""
    if entry_price <= 0.0 or position_size_signed == 0.0:
        raise ValueError(
            "break-even trigger requires a positive entry and open exposure"
        )
    sign = 1.0 if position_size_signed > 0.0 else -1.0
    return entry_price * (1.0 + sign * BREAKEVEN_BPS / 10_000.0)


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
) -> bool:
    """Attempt each requested raise at most MAX_RAISE_ATTEMPTS times per lifecycle."""
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
        attempts[key] = attempts.get(key, 0) + 1
        trigger = breakeven_trigger_price(
            venue.position.entry_price, venue.position.size_signed
        )
        raised = raise_stop(symbol, trigger)
        emit(
            "breakeven_stop_attempt",
            {
                "symbol": symbol,
                "entry_oid": entry_oid,
                "attempt": attempts[key],
                "trigger_price": trigger,
                "raised": raised,
            },
        )
        if raised:
            attempts[key] = MAX_RAISE_ATTEMPTS
            mutated = True
    return mutated
