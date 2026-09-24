"""A floor-target raise that keeps being skipped is surfaced, not silently retried.

The software floor arms and exits on completed-minute closes, so it keeps working
while no fresh two-sided book passes the executable-quote guard. The venue raise
does not: it skips that cycle without spending an attempt. A lifecycle whose raise
is skipped cycle after cycle would keep its initial venue stop for the rest of a
+2R trade with no warning, and would journal one skip row per poll.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_cohort_breakeven_floor_target import (
    NOW,
    _book,
    _plan,
    _Position,
    _stop,
    _Venue,
)

from hypervector.live.bidirectional_intents import IntentRoutingReport
from hypervector.live.cohort_breakeven_stop import (
    BREAKEVEN_SKIPPED_EVENT,
    MAX_CONSECUTIVE_SKIPS,
    MAX_RAISE_ATTEMPTS,
    RAISE_EXHAUSTED_EVENT,
    raise_breakeven_stops,
)
from hypervector.live.hyperliquid_protocol import SolBookSnapshot, SolOpenOrder
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.research.cohort_protection_warnings import protection_warnings

_ATTEMPT = "breakeven_stop_attempt"
_USABLE = _book(106.0, 106.01)
_AHEAD_OF_LOCAL_CLOCK = replace(_USABLE, exchange_timestamp_ms=NOW + 500)
_THROUGH_MARKET = _book(101.0, 101.01)


class _Cycles:
    """Drive one floor-armed long through successive polls with shared state."""

    def __init__(
        self, resting: SolOpenOrder | None = None, outcome: bool = True
    ) -> None:
        self.attempts: dict[tuple[str, int], int] = {}
        self.skips: dict[tuple[str, int], tuple[str, int]] = {}
        self.events: list[dict[str, object]] = []
        self.sent: list[float] = []
        self.resting = resting
        self.outcome = outcome

    def poll(self, book: SolBookSnapshot | None) -> bool:
        def emit(event: str, payload: Mapping[str, object]) -> None:
            self.events.append({"event": event, **payload})

        return raise_breakeven_stops(
            requests=frozenset({"xyz:SNDK"}),
            closed_symbols=set(),
            symbols=("xyz:SNDK",),
            venues={
                "xyz:SNDK": _Venue(
                    _Position(100.0, 1.0),
                    () if self.resting is None else (self.resting,),
                )
            },
            raise_stop=lambda _symbol, trigger: (
                self.sent.append(trigger) or self.outcome
            ),
            attempts=self.attempts,
            lifecycle_oids={"xyz:SNDK": 41},
            emit=emit,
            plans={"xyz:SNDK": _plan()},
            books={"xyz:SNDK": book},
            observed_ms=NOW,
            stop_oids={"xyz:SNDK": 77},
            skips=self.skips,
        )

    def kinds(self) -> list[str]:
        return [str(event["event"]) for event in self.events]


def test_skip_bound_matches_the_attempt_bound() -> None:
    assert MAX_CONSECUTIVE_SKIPS == MAX_RAISE_ATTEMPTS


@pytest.mark.parametrize("book", [None, _AHEAD_OF_LOCAL_CLOCK])
def test_an_hour_without_a_usable_quote_warns_once_and_journals_one_skip(
    book: SolBookSnapshot | None,
) -> None:
    """The reviewed case: 240 polls (1 h at 15 s) of a floor-armed long."""
    cycles = _Cycles()
    for _ in range(240):
        assert cycles.poll(book) is False
    assert cycles.sent == [] and cycles.attempts == {}
    assert cycles.kinds() == [BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT]
    skipped, exhausted = cycles.events
    assert skipped["reason"] == "executable_quote_unavailable"
    assert exhausted == {
        "event": RAISE_EXHAUSTED_EVENT,
        "symbol": "xyz:SNDK",
        "strategy_id": "hourly_donchian_20_10_atr20_v1",
        "entry_oid": 41,
        "reason": RAISE_EXHAUSTED_EVENT,
        "attempts": 0,
        "trigger_price": pytest.approx(101.25),
        "breakeven_stop_target": "floor",
        "cause": "executable_quote_unavailable",
        "skipped_cycles": MAX_CONSECUTIVE_SKIPS,
        "executable_price": None,
    }


def test_the_warning_lands_on_the_bounded_skip_cycle() -> None:
    cycles = _Cycles()
    for _ in range(MAX_CONSECUTIVE_SKIPS - 1):
        cycles.poll(None)
    assert RAISE_EXHAUSTED_EVENT not in cycles.kinds()
    cycles.poll(None)
    assert cycles.kinds()[-1] == RAISE_EXHAUSTED_EVENT


def test_skips_are_journaled_only_when_the_reason_changes() -> None:
    cycles = _Cycles()
    for book in (None, None, _THROUGH_MARKET, _THROUGH_MARKET, None):
        cycles.poll(book)
    assert cycles.kinds() == [
        BREAKEVEN_SKIPPED_EVENT,
        BREAKEVEN_SKIPPED_EVENT,
        RAISE_EXHAUSTED_EVENT,
        BREAKEVEN_SKIPPED_EVENT,
    ]
    reasons = [event.get("reason") for event in cycles.events]
    assert reasons[0] == reasons[3] == "executable_quote_unavailable"
    assert reasons[1] == "target_not_protective_of_market"
    # The streak counts consecutive skipped cycles whatever their reason.
    assert cycles.events[2]["cause"] == "target_not_protective_of_market"
    assert cycles.events[2]["executable_price"] == pytest.approx(101.0)


def test_a_sent_raise_resets_the_skip_streak() -> None:
    cycles = _Cycles(outcome=False)
    cycles.poll(None)
    cycles.poll(None)
    cycles.poll(_USABLE)
    cycles.poll(None)
    cycles.poll(None)
    assert cycles.kinds() == [
        BREAKEVEN_SKIPPED_EVENT,
        _ATTEMPT,
        BREAKEVEN_SKIPPED_EVENT,
    ]
    assert cycles.attempts == {("xyz:SNDK", 41): 1}


def test_a_venue_stop_already_at_the_target_is_not_a_skip_warning() -> None:
    """A restart after a raise has an empty skip streak but a raised stop."""
    cycles = _Cycles(resting=_stop(101.25))
    for _ in range(MAX_CONSECUTIVE_SKIPS + 2):
        cycles.poll(None)
    assert cycles.kinds() == [BREAKEVEN_SKIPPED_EVENT]


def test_raise_after_the_warning_clears_the_protection_warning() -> None:
    """End to end: minute-close floor, no fresh book, then a book returns."""
    cycles = _Cycles()
    for _ in range(MAX_CONSECUTIVE_SKIPS):
        cycles.poll(None)
    rows = [
        {
            "event_type": event["event"],
            "observed_at_utc": f"2026-09-24T18:0{index}:00+00:00",
            "payload": {key: value for key, value in event.items() if key != "event"},
        }
        for index, event in enumerate(cycles.events)
    ]
    snapshot = {
        "event_type": "cohort_snapshot",
        "payload": {
            "assets": [
                {"symbol": "xyz:SNDK", "entry_oid": 41, "position_size_signed": 1.0}
            ]
        },
    }
    assert protection_warnings(rows, snapshot) == [
        {
            "symbol": "xyz:SNDK",
            "strategy_id": "hourly_donchian_20_10_atr20_v1",
            "entry_oid": 41,
            "reason": "protective_stop_raise_exhausted",
            "observed_at_utc": rows[-1]["observed_at_utc"],
        }
    ]
    assert cycles.poll(_USABLE) is True
    raised = cycles.events[-1]
    assert raised["event"] == _ATTEMPT and raised["raised"] is True
    rows.append(
        {
            "event_type": _ATTEMPT,
            "observed_at_utc": "2026-09-24T18:09:00+00:00",
            "payload": {key: value for key, value in raised.items() if key != "event"},
        }
    )
    assert protection_warnings(rows, snapshot) == []


def test_the_runner_keeps_the_skip_streak_across_polls() -> None:
    runner = MultiAssetLiveRunner.__new__(MultiAssetLiveRunner)
    runner._assign_operator_dependencies(  # type: ignore[attr-defined]
        None, Mock(), {}, frozenset(), frozenset(), 1, None
    )
    assert runner._breakeven_skips == {}  # type: ignore[attr-defined]
    engine = Mock()
    engine.snapshot = SimpleNamespace(entry_oid=41, stop_oid=77, execution_plan=_plan())
    engine.latest_book = None
    engine.normalize_trigger_price.side_effect = lambda price: price
    events: list[str] = []
    runner._symbols = ("xyz:SNDK",)  # type: ignore[attr-defined]
    runner._engines = {"xyz:SNDK": engine}  # type: ignore[attr-defined]
    runner._profit_lock_controller = SimpleNamespace(  # type: ignore[attr-defined]
        breakeven_requests=frozenset({"xyz:SNDK"})
    )
    runner._telemetry = SimpleNamespace(  # type: ignore[attr-defined]
        emit_breakeven_stop_attempt=lambda event, _payload: events.append(event)
    )
    venues = (_Venue(_Position(100.0, 1.0), (_stop(97.5),)),)
    report = IntentRoutingReport((), ())
    for _ in range(10):
        assert runner._raise_breakeven_stops(report, venues, NOW) is False
    assert events == [BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT]
    engine.raise_protective_stop.assert_not_called()
