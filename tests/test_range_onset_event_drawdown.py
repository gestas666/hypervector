"""Tests for sampled-mark event-replay drawdown."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.mark_stop_trigger import SampledMarkSeries
from hypervector.research.market_depth_database import TimedMarketDepthFill
from hypervector.research.market_depth_fill import MarketDepthFill, MarketSide
from hypervector.research.range_onset_event_drawdown import (
    with_mark_to_market_drawdown,
)
from hypervector.research.range_onset_event_replay import (
    EventReplayConfig,
    EventSignal,
    replay_range_onset_events,
)
from hypervector.research.shared_portfolio_models import Direction


def _fill(
    event_time_ms: int,
    side: MarketSide,
    quantity: float,
) -> TimedMarketDepthFill:
    depth = MarketDepthFill(
        side, quantity, quantity, 0.0, 100.0, 100.0, 100.0, 0.0, 1, True
    )
    return TimedMarketDepthFill(event_time_ms, event_time_ms + 5, 5, depth)


def _no_crossing(
    _direction: Direction,
    _price: float,
    _start_ms: int,
    _end_ms: int,
) -> int | None:
    return None


def test_sampled_drawdown_captures_unrealized_path_and_exit_equity() -> None:
    """Intratrade adverse marks must appear beyond realized-only drawdown."""
    report = replay_range_onset_events(
        (EventSignal(1_000, 100.0, True, False, False, False),),
        (),
        EventReplayConfig(initial_equity=1_000.0),
        market_fill=_fill,
        stop_crossing=_no_crossing,
        end_time_ms=4_000,
    )
    marks = SampledMarkSeries(
        pd.DataFrame(
            {
                "ts_ms": [1_005, 2_000, 3_000, 4_000],
                "mark_price": [100.0, 90.0, 110.0, 100.0],
            }
        ),
        maximum_gap_ms=1_000,
    )

    measured = with_mark_to_market_drawdown(report, (), marks)

    assert report.realized_maximum_drawdown_pct == pytest.approx(-0.045)
    assert measured.mark_to_market_maximum_drawdown_pct == pytest.approx(-5.0225)
    assert measured.mark_to_market_unobserved_trades == 0
