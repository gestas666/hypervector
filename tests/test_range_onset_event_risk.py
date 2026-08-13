"""Tests for funding-aware event-replay liquidation ordering."""

from __future__ import annotations

import pytest

from hypervector.research.range_onset_event_models import (
    EventFunding,
    EventReplayConfig,
)
from hypervector.research.range_onset_event_risk import (
    EventRiskPosition,
    first_risk_crossing,
    funding_cashflow,
    liquidation_price,
)
from hypervector.research.shared_portfolio_models import Direction


def _long_position() -> EventRiskPosition:
    return EventRiskPosition("long", 5.0, 100.0, 100.0, 0.225, 1_000, 99.4)


def test_long_liquidation_price_includes_entry_fee() -> None:
    """The isolated boundary must use collateral net of paid entry fees."""
    price = liquidation_price(
        _long_position(), EventReplayConfig(initial_equity=1_000.0), 0.0
    )

    assert price == pytest.approx(82.0974359)


def test_funding_changes_liquidation_boundary_only_after_settlement() -> None:
    """Funding must produce chronological liquidation-boundary intervals."""
    position = _long_position()
    config = EventReplayConfig(initial_equity=1_000.0)
    event = EventFunding(2_000, 0.01, 100.0)
    queried: list[tuple[float, int, int]] = []

    def crossing(
        _direction: Direction,
        boundary: float,
        start_time_ms: int,
        end_time_ms: int,
    ) -> int | None:
        queried.append((boundary, start_time_ms, end_time_ms))
        if boundary > 83.0:
            return 2_500
        return None

    result = first_risk_crossing(position, (event,), config, crossing, 3_000)

    assert funding_cashflow(position, event) == pytest.approx(-5.0)
    assert result is not None
    assert result.reason == "liquidation"
    assert result.event_time_ms == 2_500
    assert len(queried) == 3
    assert queried[-2][1:] == (1_000, 2_000)
    assert queried[-1][1:] == (2_000, 2_501)
    assert queried[-1][0] == pytest.approx(83.1230769)


def test_future_funding_cannot_retroactively_liquidate_position() -> None:
    """A later adverse funding payment must not move the earlier boundary."""
    position = _long_position()
    event = EventFunding(2_000, 0.01, 100.0)

    def crossing(
        _direction: Direction,
        boundary: float,
        start_time_ms: int,
        _end_time_ms: int,
    ) -> int | None:
        return start_time_ms + 100 if 83.0 < boundary < 90.0 else None

    result = first_risk_crossing(
        position,
        (event,),
        EventReplayConfig(initial_equity=1_000.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "liquidation"
    assert result.event_time_ms == 2_100


def test_stop_wins_when_it_precedes_liquidation() -> None:
    """Chronological ordering must preserve an earlier ordinary stop."""
    position = _long_position()

    def crossing(
        _direction: Direction,
        boundary: float,
        _start_time_ms: int,
        _end_time_ms: int,
    ) -> int | None:
        return 1_500 if boundary > 90.0 else 2_000

    result = first_risk_crossing(
        position,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "stop"
    assert result.event_time_ms == 1_500


def test_liquidation_search_stops_at_known_ordinary_stop() -> None:
    """Evidence after an observed stop cannot affect exit ordering."""
    position = _long_position()
    queried: list[tuple[float, int]] = []

    def crossing(
        _direction: Direction,
        boundary: float,
        _start_time_ms: int,
        end_time_ms: int,
    ) -> int | None:
        queried.append((boundary, end_time_ms))
        return 1_500 if boundary > 90.0 else None

    result = first_risk_crossing(
        position,
        (),
        EventReplayConfig(initial_equity=1_000.0),
        crossing,
        3_000,
    )

    assert result is not None
    assert result.reason == "stop"
    assert queried[1][1] == 1_501
