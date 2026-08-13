"""Report-only counterfactual peak-protection observation."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from hypervector.paper.book import BookSnapshot
from hypervector.strategies.peak_observer_contract import (
    PEAK_OBSERVER_CANDIDATE_ID,
    PEAK_OBSERVER_SCHEMA,
    PeakObserverConfig,
)

__all__ = [
    "PEAK_OBSERVER_CANDIDATE_ID",
    "PEAK_OBSERVER_SCHEMA",
    "PeakDirection",
    "PeakObserverConfig",
    "PeakObserverState",
    "PeakProtectionObserver",
]

PeakDirection = Literal["long", "short"]


@dataclass(frozen=True)
class PeakObserverState:
    """Durable state for one actual backend position lifecycle."""

    direction: PeakDirection
    quantity: float
    entry_price: float
    position_started_at: str
    coverage_complete_since_entry: bool
    peak_margin_pct: float = 0.0
    locked_margin_pct: float | None = None
    hypothetical_stop_price: float | None = None
    last_sample_at: str | None = None
    last_update_at: str | None = None
    trigger_unpriced_at: str | None = None
    hypothetical_exit_at: str | None = None
    hypothetical_exit_price: float | None = None
    hypothetical_exit_fee_usd: float | None = None


class PeakProtectionObserver:
    """Observe a counterfactual peak lock without mutating execution state."""

    def __init__(
        self,
        *,
        config: PeakObserverConfig,
        leverage: float,
        taker_fee_rate: float,
        initial_state: PeakObserverState | None = None,
    ) -> None:
        _positive(leverage, "leverage")
        _rate(taker_fee_rate, "taker_fee_rate")
        self._config = config
        self._leverage = leverage
        self._taker_fee_rate = taker_fee_rate
        self._state = initial_state

    @property
    def state(self) -> PeakObserverState | None:
        """Return the current immutable observer state."""
        return self._state

    def sync_position(
        self,
        *,
        quantity: float,
        average_price: float | None,
        observed_at: str,
        coverage_complete_since_entry: bool,
    ) -> tuple[dict[str, object], ...]:
        """Synchronize actual position identity without changing that position."""
        _finite(quantity, "quantity")
        _timestamp(observed_at)
        if self._config.mode == "off":
            return ()
        if abs(quantity) <= 1e-12:
            return self._end_position(observed_at)
        if average_price is None:
            raise ValueError("open observer position requires average_price")
        _positive(average_price, "average_price")
        direction: PeakDirection = "long" if quantity > 0.0 else "short"
        if self._state is None:
            self._state = PeakObserverState(
                direction=direction,
                quantity=abs(quantity),
                entry_price=average_price,
                position_started_at=observed_at,
                coverage_complete_since_entry=coverage_complete_since_entry,
            )
            return (self._event("peak_observer_position_start", observed_at),)
        if self._state.direction != direction:
            raise RuntimeError("observer position direction changed without flat state")
        stop = self._revalued_stop(average_price)
        self._state = replace(
            self._state,
            quantity=abs(quantity),
            entry_price=average_price,
            hypothetical_stop_price=stop,
        )
        return ()

    def observe_mark(
        self,
        *,
        mark_price: float,
        observed_at: str,
        book: BookSnapshot | None,
        evidence_fresh: bool,
    ) -> tuple[dict[str, object], ...]:
        """Sample one causal mark and emit only observer state changes."""
        _positive(mark_price, "mark_price")
        now = _timestamp(observed_at)
        state = self._state
        if self._config.mode == "off" or state is None:
            return ()
        if state.hypothetical_exit_at is not None or not self._sample_due(state, now):
            return ()
        margin_pct = _margin_pct(state, mark_price, self._leverage)
        self._state = replace(
            state,
            peak_margin_pct=max(state.peak_margin_pct, margin_pct),
            last_sample_at=observed_at,
        )
        transition = self._update_protection(now, observed_at)
        trigger = self._trigger(mark_price, observed_at, book, evidence_fresh)
        if transition is None and trigger is None:
            return ()
        return tuple(event for event in (transition, trigger) if event is not None)

    def _sample_due(self, state: PeakObserverState, now: datetime) -> bool:
        if state.last_sample_at is None:
            return True
        elapsed = (now - _timestamp(state.last_sample_at)).total_seconds()
        if elapsed < 0.0:
            raise ValueError("observer marks must be time ordered")
        return elapsed >= self._config.sample_interval_seconds

    def _update_protection(
        self,
        now: datetime,
        observed_at: str,
    ) -> dict[str, object] | None:
        state = self._required_state()
        activated = state.peak_margin_pct >= self._config.activation_margin_pct
        activated = activated or math.isclose(
            state.peak_margin_pct,
            self._config.activation_margin_pct,
            abs_tol=1e-9,
        )
        if not activated:
            return None
        locked = state.peak_margin_pct * self._config.lock_ratio
        desired = _stop_price(
            state.direction, state.entry_price, locked, self._leverage
        )
        if state.hypothetical_stop_price is None:
            self._state = replace(
                state,
                locked_margin_pct=locked,
                hypothetical_stop_price=desired,
                last_update_at=observed_at,
            )
            return self._event("peak_observer_armed", observed_at)
        if not self._can_ratchet(state, desired, now):
            return None
        self._state = replace(
            state,
            locked_margin_pct=locked,
            hypothetical_stop_price=desired,
            last_update_at=observed_at,
        )
        return self._event("peak_observer_updated", observed_at)

    def _can_ratchet(
        self,
        state: PeakObserverState,
        desired: float,
        now: datetime,
    ) -> bool:
        current = state.hypothetical_stop_price
        if current is None or state.last_update_at is None:
            return False
        improvement = (
            desired - current if state.direction == "long" else current - desired
        )
        minimum = state.entry_price * self._config.minimum_stop_move_fraction
        elapsed = (now - _timestamp(state.last_update_at)).total_seconds()
        return (
            improvement >= minimum and elapsed >= self._config.update_cooldown_seconds
        )

    def _trigger(
        self,
        mark_price: float,
        observed_at: str,
        book: BookSnapshot | None,
        evidence_fresh: bool,
    ) -> dict[str, object] | None:
        state = self._required_state()
        stop = state.hypothetical_stop_price
        if stop is None or not _is_triggered(state.direction, mark_price, stop):
            return None
        exit_price = _adverse_bbo(state.direction, book) if evidence_fresh else None
        if exit_price is None:
            if state.trigger_unpriced_at is not None:
                return None
            self._state = replace(
                state,
                coverage_complete_since_entry=False,
                trigger_unpriced_at=observed_at,
            )
            return self._event("peak_observer_trigger_unpriced", observed_at)
        fee = state.quantity * exit_price * self._taker_fee_rate
        self._state = replace(
            state,
            hypothetical_exit_at=observed_at,
            hypothetical_exit_price=exit_price,
            hypothetical_exit_fee_usd=fee,
        )
        return self._event("peak_observer_would_exit", observed_at)

    def _revalued_stop(self, average_price: float) -> float | None:
        state = self._required_state()
        locked = state.locked_margin_pct
        if locked is None:
            return None
        return _stop_price(state.direction, average_price, locked, self._leverage)

    def _end_position(self, observed_at: str) -> tuple[dict[str, object], ...]:
        if self._state is None:
            return ()
        event = self._event(
            "peak_observer_position_end",
            observed_at,
            observer_active=False,
        )
        self._state = None
        return (event,)

    def _required_state(self) -> PeakObserverState:
        if self._state is None:
            raise RuntimeError("peak observer has no active position")
        return self._state

    def _event(
        self,
        action: str,
        observed_at: str,
        *,
        observer_active: bool = True,
    ) -> dict[str, object]:
        state = self._required_state()
        trigger_status = "not_triggered"
        if state.hypothetical_exit_at is not None:
            trigger_status = "fresh_bbo"
        elif state.trigger_unpriced_at is not None:
            trigger_status = "stale_or_missing_book"
        return {
            "feed_ts": observed_at,
            "action": action,
            "observer_schema": PEAK_OBSERVER_SCHEMA,
            "candidate_id": self._config.candidate_id,
            "observer_active": observer_active,
            "position_direction": state.direction,
            "position_quantity": state.quantity,
            "position_entry_price": state.entry_price,
            "position_started_at": state.position_started_at,
            "coverage_complete_since_entry": state.coverage_complete_since_entry,
            "peak_margin_pct": state.peak_margin_pct,
            "locked_margin_pct": state.locked_margin_pct,
            "hypothetical_stop_price": state.hypothetical_stop_price,
            "last_sample_at": state.last_sample_at,
            "last_update_at": state.last_update_at,
            "trigger_unpriced_at": state.trigger_unpriced_at,
            "hypothetical_exit_at": state.hypothetical_exit_at,
            "hypothetical_exit_price": state.hypothetical_exit_price,
            "hypothetical_exit_fee_usd": state.hypothetical_exit_fee_usd,
            "trigger_evidence_status": trigger_status,
            "execution_authority": "none",
            "report_only": True,
            "submitted": False,
            "place_attempted": False,
        }


def _margin_pct(
    state: PeakObserverState,
    mark_price: float,
    leverage: float,
) -> float:
    sign = 1.0 if state.direction == "long" else -1.0
    return (
        sign * (mark_price - state.entry_price) / state.entry_price * leverage * 100.0
    )


def _stop_price(
    direction: PeakDirection,
    entry_price: float,
    locked_margin_pct: float,
    leverage: float,
) -> float:
    sign = 1.0 if direction == "long" else -1.0
    fraction = locked_margin_pct / (leverage * 100.0)
    return entry_price * (1.0 + sign * fraction)


def _is_triggered(
    direction: PeakDirection,
    mark_price: float,
    stop_price: float,
) -> bool:
    if direction == "long":
        return mark_price <= stop_price
    return mark_price >= stop_price


def _adverse_bbo(
    direction: PeakDirection,
    book: BookSnapshot | None,
) -> float | None:
    if book is None:
        return None
    price = book.best_bid() if direction == "long" else book.best_ask()
    if price is None or not math.isfinite(price) or price <= 0.0:
        return None
    return price


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observer timestamp must be ISO-8601") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("observer timestamp must use UTC")
    return parsed


def _finite(value: float, field: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"peak observer {field} must be finite")


def _positive(value: float, field: str) -> None:
    _finite(value, field)
    if value <= 0.0:
        raise ValueError(f"peak observer {field} must be positive")


def _rate(value: float, field: str) -> None:
    _finite(value, field)
    if not 0.0 <= value < 1.0:
        raise ValueError(f"peak observer {field} must be in [0, 1)")
