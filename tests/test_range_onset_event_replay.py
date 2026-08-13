"""Tests for chronological range-onset event execution."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from hypervector.research.market_depth_database import TimedMarketDepthFill
from hypervector.research.market_depth_fill import MarketDepthFill, MarketSide
from hypervector.research.range_onset_event_replay import (
    EventFunding,
    EventReplayConfig,
    EventSignal,
    replay_range_onset_events,
)
from hypervector.research.shared_portfolio_models import Direction


def _complete_fill(
    event_time_ms: int,
    side: MarketSide,
    quantity: float,
    price: float,
) -> TimedMarketDepthFill:
    fill = MarketDepthFill(
        side,
        quantity,
        quantity,
        0.0,
        price,
        price,
        price,
        0.0,
        1,
        True,
    )
    return TimedMarketDepthFill(event_time_ms, event_time_ms + 5, 5, fill)


def _fill_source(
    prices: dict[tuple[int, MarketSide], list[float]],
) -> Callable[[int, MarketSide, float], TimedMarketDepthFill]:
    def fill(
        event_time_ms: int,
        side: MarketSide,
        quantity: float,
    ) -> TimedMarketDepthFill:
        values = prices[(event_time_ms, side)]
        return _complete_fill(event_time_ms, side, quantity, values.pop(0))

    return fill


def _no_stop(
    _direction: Direction,
    _stop_price: float,
    _start_time_ms: int,
    _end_time_ms: int,
) -> int | None:
    return None


def test_replay_executes_long_stop_with_fees_and_actual_depth_prices() -> None:
    """A stop lifecycle must compound actual fills and both taker fees."""
    events = (EventSignal(1_000, 100.0, True, False, False, False),)

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill_source({(1_000, "buy"): [100.0], (1_500, "sell"): [99.0]}),
        stop_crossing=lambda _direction, boundary, *_times: (
            1_500 if boundary > 90.0 else None
        ),
        end_time_ms=3_000,
    )

    assert report.status == "complete"
    assert report.completed_trades == 1
    assert report.mark_to_market_maximum_drawdown_pct is None
    assert report.mark_to_market_unobserved_trades is None
    trade = report.trades[0]
    assert trade.direction == "long"
    assert trade.exit_reason == "stop"
    assert trade.stop_price == pytest.approx(99.4)
    assert trade.net_pnl_usd == pytest.approx(-5.44775)
    assert report.final_equity == pytest.approx(994.55225)


def test_replay_executes_configured_target_before_later_signal() -> None:
    """An optional target must close with the first executable depth fill."""
    events = (
        EventSignal(1_000, 100.0, True, False, False, False),
        EventSignal(2_500, 101.0, False, False, True, False),
    )

    def crossing(
        direction: Direction,
        boundary: float,
        _start_ms: int,
        _end_ms: int,
    ) -> int | None:
        return 1_500 if direction == "short" and boundary > 100.0 else None

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0, target_bps=60.0),
        market_fill=_fill_source({(1_000, "buy"): [100.0], (1_500, "sell"): [100.6]}),
        stop_crossing=crossing,
        end_time_ms=3_000,
    )

    assert report.completed_trades == 1
    assert report.trades[0].exit_reason == "target"
    assert report.trades[0].net_pnl_usd == pytest.approx(2.54865)


def test_replay_closes_and_reverses_on_same_opposite_signal() -> None:
    """An eligible opposite onset closes first, then opens the new side."""
    events = (
        EventSignal(1_000, 100.0, True, False, False, False),
        EventSignal(2_000, 101.0, False, True, True, False),
    )
    prices = {
        (1_000, "buy"): [100.0],
        (2_000, "sell"): [101.0, 101.0],
        (2_999, "buy"): [100.0],
    }

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill_source(prices),
        stop_crossing=_no_stop,
        end_time_ms=3_000,
    )

    assert report.status == "complete"
    assert report.completed_trades == 2
    assert [trade.direction for trade in report.trades] == ["long", "short"]
    assert [trade.exit_reason for trade in report.trades] == [
        "opposite_signal",
        "end_of_data",
    ]


def test_replay_continues_to_later_entry_after_maximum_hold() -> None:
    """A maximum-hold close must not discard every later signal event."""
    events = (
        EventSignal(1_000, 100.0, True, False, False, False),
        EventSignal(5_000, 100.0, False, True, False, False),
    )
    prices = {
        (1_000, "buy"): [100.0],
        (2_005, "sell"): [100.0],
        (5_000, "sell"): [100.0],
        (6_005, "buy"): [100.0],
    }

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(
            initial_equity=1_000.0,
            max_hold_ms=1_000,
            reentry_cooldown_ms=100,
        ),
        market_fill=_fill_source(prices),
        stop_crossing=_no_stop,
        end_time_ms=7_000,
    )

    assert report.completed_trades == 2
    assert [trade.direction for trade in report.trades] == ["long", "short"]
    assert [trade.exit_reason for trade in report.trades] == [
        "max_hold",
        "max_hold",
    ]


def test_replay_applies_funding_cashflow_before_next_position_size() -> None:
    """Venue funding must affect realized equity and subsequent compounding."""
    events = (EventSignal(1_000, 100.0, True, False, False, False),)
    funding = (EventFunding(1_200, 0.01, 100.0),)

    report = replay_range_onset_events(
        events,
        funding,
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill_source({(1_000, "buy"): [100.0], (2_999, "sell"): [100.0]}),
        stop_crossing=_no_stop,
        end_time_ms=3_000,
    )

    trade = report.trades[0]
    assert trade.funding_cashflow_usd == pytest.approx(-5.0)
    assert trade.net_pnl_usd == pytest.approx(-5.45)
    assert report.final_equity == pytest.approx(994.55)


def test_replay_terminates_explicitly_on_visible_depth_shortfall() -> None:
    """Insufficient recorded depth must not become a synthetic full fill."""
    events = (EventSignal(1_000, 100.0, True, False, False, False),)

    def incomplete(
        event_time_ms: int,
        side: MarketSide,
        quantity: float,
    ) -> TimedMarketDepthFill:
        fill = MarketDepthFill(
            side,
            quantity,
            quantity / 2.0,
            quantity / 2.0,
            100.0,
            100.0,
            100.0,
            0.0,
            1,
            False,
        )
        return TimedMarketDepthFill(event_time_ms, event_time_ms, 0, fill)

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=incomplete,
        stop_crossing=_no_stop,
        end_time_ms=3_000,
    )

    assert report.status == "depth_failure"
    assert report.completed_trades == 0
    assert report.failure is not None
    assert "visible depth" in report.failure


def test_replay_counts_conflicting_entry_signal_without_opening() -> None:
    """Simultaneous long and short entries are explicit conflicts."""
    events = (EventSignal(1_000, 100.0, True, True, False, False),)

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=lambda *_args: pytest.fail("conflict must not execute"),
        stop_crossing=_no_stop,
        end_time_ms=3_000,
    )

    assert report.status == "complete"
    assert report.completed_trades == 0
    assert report.conflicting_entry_signals == 1


def test_replay_prioritizes_liquidation_when_one_gap_crosses_both_barriers() -> None:
    """A sampled gap beyond stop and liquidation must take the adverse outcome."""
    events = (EventSignal(1_000, 100.0, True, False, False, False),)

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill_source({(1_000, "buy"): [100.0], (1_500, "sell"): [80.0]}),
        stop_crossing=lambda *_args: 1_500,
        end_time_ms=3_000,
    )

    assert report.status == "complete"
    assert report.liquidations == 1
    assert report.trades[0].exit_reason == "liquidation"
    assert report.trades[0].liquidation_price == pytest.approx(82.0974359)


def test_replay_uses_stop_when_liquidation_boundary_was_not_crossed() -> None:
    """A normal stop crossing must remain a stop when mark stays above liquidation."""
    events = (EventSignal(1_000, 100.0, True, False, False, False),)

    def crossing(
        _direction: Direction,
        boundary: float,
        _start_time_ms: int,
        _end_time_ms: int,
    ) -> int | None:
        return 1_500 if boundary > 90.0 else None

    report = replay_range_onset_events(
        events,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill_source({(1_000, "buy"): [100.0], (1_500, "sell"): [99.0]}),
        stop_crossing=crossing,
        end_time_ms=3_000,
    )

    assert report.liquidations == 0
    assert report.trades[0].exit_reason == "stop"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"margin_fraction": 0.0}, "margin_fraction"),
        ({"leverage": 21.0}, "venue_max_leverage"),
        ({"stop_bps": -1.0}, "stop_bps"),
        ({"max_hold_ms": 0}, "max_hold_ms"),
        ({"target_bps": 0.0}, "target_bps"),
    ],
)
def test_event_replay_config_rejects_invalid_risk_contract(
    changes: dict[str, object],
    message: str,
) -> None:
    """Risk and venue violations fail before event execution."""
    values: dict[str, object] = {}
    values.update(changes)
    with pytest.raises(ValueError, match=message):
        EventReplayConfig(**values)  # type: ignore[arg-type]
