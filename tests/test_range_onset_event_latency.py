"""Measured decision-latency tests for range-onset event replay."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from hypervector.research.market_depth_database import TimedMarketDepthFill
from hypervector.research.market_depth_fill import MarketDepthFill, MarketSide
from hypervector.research.range_onset_event_replay import (
    EventReplayConfig,
    EventSignal,
    replay_range_onset_events,
)
from hypervector.research.shared_portfolio_models import Direction


def _fills(
    observed: list[tuple[int, MarketSide]],
) -> Callable[[int, MarketSide, float], TimedMarketDepthFill]:
    def fill(
        event_time_ms: int,
        side: MarketSide,
        quantity: float,
    ) -> TimedMarketDepthFill:
        observed.append((event_time_ms, side))
        result = MarketDepthFill(
            side,
            quantity,
            quantity,
            0.0,
            100.0,
            100.0,
            100.0,
            0.0,
            1,
            True,
        )
        return TimedMarketDepthFill(event_time_ms, event_time_ms + 5, 5, result)

    return fill


def _no_stop(
    _direction: Direction,
    _price: float,
    _start_ms: int,
    _end_ms: int,
) -> int | None:
    return None


def test_decision_delay_applies_to_entry_and_signal_exit() -> None:
    """Strategy decisions should reach depth only after measured delay."""
    calls: list[tuple[int, MarketSide]] = []
    events = (
        EventSignal(1_000, 100.0, True, False, False, False),
        EventSignal(4_000, 100.0, False, False, True, False),
    )

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0, decision_delay_ms=8_000),
        market_fill=_fills(calls),
        stop_crossing=_no_stop,
        end_time_ms=20_000,
    )

    assert calls == [(9_000, "buy"), (12_000, "sell")]
    trade = report.trades[0]
    assert trade.entry_decision_time_ms == 1_000
    assert trade.entry_latency_ms == 8_005
    assert trade.exit_event_time_ms == 4_000
    assert trade.exit_latency_ms == 8_005


def test_venue_stop_trigger_does_not_wait_for_decision_delay() -> None:
    """A pre-positioned venue stop should execute from its mark trigger time."""
    calls: list[tuple[int, MarketSide]] = []

    report = replay_range_onset_events(
        (EventSignal(1_000, 100.0, True, False, False, False),),
        (),
        EventReplayConfig(initial_equity=1_000.0, decision_delay_ms=8_000),
        market_fill=_fills(calls),
        stop_crossing=lambda _direction, price, *_times: (
            10_000 if price > 90.0 else None
        ),
        end_time_ms=20_000,
    )

    assert calls == [(9_000, "buy"), (10_000, "sell")]
    assert report.trades[0].exit_reason == "stop"
    assert report.trades[0].exit_latency_ms == 5


def test_decision_delay_must_be_non_negative() -> None:
    """Negative reaction time is invalid rather than a faster scenario."""
    with pytest.raises(ValueError, match="decision_delay_ms"):
        EventReplayConfig(decision_delay_ms=-1)
