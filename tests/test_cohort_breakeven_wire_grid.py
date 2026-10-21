"""Break-even raises compare the target with the venue stop on the wire price grid.

The adapter rounds every trigger to Hyperliquid's five-significant-figure perp
grid before it reaches the wire, so after a restart the owned venue stop carries
the rounded trigger while the break-even target is recomputed unrounded. When
nearest rounding went against the position, the unrounded target looked more
favorable than the resting stop: the engine sent a live modify carrying the
identical wire price, and the exhaustion check warned about a stop that was
already raised. Both comparisons now use the adapter's own wire normalization.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_cohort_breakeven_engine import _open, _rows
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
    breakeven_target_price,
    raise_breakeven_stops,
)
from hypervector.live.hyperliquid_sol_parsing import normalize_perp_price
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_order_submission import SolOrderSubmission
from hypervector.live.sol_range_onset_engine_contract import STOP_ALREADY_AT_TARGET
from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.research.cohort_protection_warnings import protection_warnings

_ATTEMPT = "breakeven_stop_attempt"
_CCC_SIZE_DECIMALS = 3  # the replay fixture's xyz:CCC szDecimals
_VENUE_ROWS = {"order_intent", "stop_order", "protective_stop_raised"}


def _wire(price: float) -> float:
    return normalize_perp_price(price, _CCC_SIZE_DECIMALS)


def _grid(_symbol: str, price: float) -> float:
    return _wire(price)


# Entry prices whose break-even target nearest-rounds each way on the wire, for
# both the floor (+/-1.25%) and the entry-offset (+/-0.25%) targets.
_ROUNDING = [
    pytest.param(1.0, 100.0037, True, id="long-rounds-down-against"),
    pytest.param(1.0, 99.9996, False, id="long-rounds-up-beyond"),
    pytest.param(-1.0, 99.9996, True, id="short-rounds-up-against"),
    pytest.param(-1.0, 100.0004, False, id="short-rounds-down-beyond"),
]


def _require_rounding(target: float, size: float, against: bool) -> float:
    """Return the wire trigger after checking the case rounds the stated way."""
    wire = _wire(target)
    assert wire != target
    rounded_down = wire < target
    assert rounded_down is ((size > 0.0) is against)
    return wire


# --------------------------------------------------------------------------- #
# engine: a real adapter and the replay venue
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "side,raised,retarget",
    [
        pytest.param("long", 100.25, 100.2549, id="long-rounds-down-against"),
        pytest.param("long", 100.25, 100.2451, id="long-rounds-up-beyond"),
        pytest.param("short", 99.75, 99.7496, id="short-rounds-up-against"),
        pytest.param("short", 99.75, 99.7504, id="short-rounds-down-beyond"),
    ],
)
def test_a_restart_retarget_rounding_onto_the_resting_stop_makes_no_venue_call(
    tmp_path: Path, side: str, raised: float, retarget: float
) -> None:
    replay, engine, symbol = _open(tmp_path, side)
    assert engine.raise_protective_stop(trigger_price=raised) is True
    resting = engine.snapshot.stop_oid
    restarted = replay.engine(replay.assets[symbol])
    assert restarted.start().stop_oid == resting
    assert replay.adapters[symbol].normalize_trigger_price(retarget) == raised
    mutations = list(replay.mutations)
    before = len(_rows(tmp_path, symbol))

    outcome = restarted.raise_protective_stop(trigger_price=retarget)

    assert outcome is STOP_ALREADY_AT_TARGET and not outcome
    assert replay.mutations == mutations
    assert restarted.snapshot.state is SolLiveState.OPEN
    assert restarted.snapshot.stop_oid == resting and resting in replay.orders
    written = _rows(tmp_path, symbol)[before:]
    assert not [row for row in written if row["event_type"] in _VENUE_ROWS]


@pytest.mark.parametrize(
    "side,raised,beyond,expected",
    [("long", 100.25, 100.2551, 100.26), ("short", 99.75, 99.7494, 99.749)],
)
def test_a_target_one_wire_tick_beyond_the_resting_stop_still_raises(
    tmp_path: Path, side: str, raised: float, beyond: float, expected: float
) -> None:
    replay, engine, symbol = _open(tmp_path, side)
    assert engine.raise_protective_stop(trigger_price=raised) is True
    restarted = replay.engine(replay.assets[symbol])
    restarted.start()

    assert restarted.raise_protective_stop(trigger_price=beyond) is True

    assert replay.mutations[-1] == "modify"
    resting = replay.orders[restarted.snapshot.stop_oid]
    assert float(resting["triggerPx"]) == expected
    assert replay.adapters[symbol].normalize_trigger_price(beyond) == expected


def test_the_adapter_normalization_is_the_wire_rounding_of_its_stop_orders(
    tmp_path: Path,
) -> None:
    replay, _engine, symbol = _open(tmp_path, "long")
    adapter = replay.adapters[symbol]
    for price in (100.2549, 100.2451, 99.7496, 97.123456, 1234.5678):
        assert adapter.normalize_trigger_price(price) == _wire(price)
    initial = next(order for order in replay.orders.values() if order["isTrigger"])
    assert adapter.normalize_trigger_price(float(initial["triggerPx"])) == float(
        initial["triggerPx"]
    )


def test_the_order_layer_delegates_normalization_and_keeps_bare_adapters_exact() -> (
    None
):
    def orders(adapter: object) -> SolOrderSubmission:
        return SolOrderSubmission(
            adapter=adapter,  # type: ignore[arg-type]
            events=Mock(),
            client_order_id_fn=Mock(side_effect=AssertionError("no order identity")),
        )

    grid = SimpleNamespace(normalize_trigger_price=lambda price: round(price, 2))
    assert orders(grid).normalize_trigger_price(100.2549) == 100.25
    assert orders(SimpleNamespace()).normalize_trigger_price(100.2549) == 100.2549


# --------------------------------------------------------------------------- #
# break-even raise bookkeeping
# --------------------------------------------------------------------------- #


class _Polls:
    """Drive one lifecycle through successive polls with shared runner state."""

    def __init__(
        self,
        *,
        target: str,
        size: float,
        entry: float,
        resting: float | None,
        outcome: object = False,
        normalize: Callable[[str, float], float] | None = _grid,
    ) -> None:
        self.plan = _plan(target)
        self.size, self.entry, self.outcome = size, entry, outcome
        self.resting = None if resting is None else _stop(resting)
        self.normalize = normalize
        self.attempts: dict[tuple[str, int], int] = {}
        self.skips: dict[tuple[str, int], tuple[str, int]] = {}
        self.events: list[dict[str, object]] = []
        self.sent: list[float] = []

    @property
    def target(self) -> float:
        return breakeven_target_price(self.plan, self.entry, self.size)

    def poll(self, book: object = None) -> bool:
        def emit(event: str, payload: Mapping[str, object]) -> None:
            self.events.append({"event": event, **payload})

        def raise_stop(_symbol: str, trigger: float) -> object:
            self.sent.append(trigger)
            return self.outcome

        extra = {} if self.normalize is None else {"normalize": self.normalize}
        return raise_breakeven_stops(
            requests=frozenset({"xyz:CCC"}),
            closed_symbols=set(),
            symbols=("xyz:CCC",),
            venues={
                "xyz:CCC": _Venue(
                    _Position(self.entry, self.size),
                    () if self.resting is None else (self.resting,),
                )
            },
            raise_stop=raise_stop,  # type: ignore[arg-type]
            attempts=self.attempts,
            lifecycle_oids={"xyz:CCC": 41},
            emit=emit,
            plans={"xyz:CCC": self.plan},
            books={"xyz:CCC": book},  # type: ignore[dict-item]
            observed_ms=NOW,
            stop_oids={"xyz:CCC": 77},
            skips=self.skips,
            **extra,  # type: ignore[arg-type]
        )

    def kinds(self) -> list[str]:
        return [str(event["event"]) for event in self.events]


@pytest.mark.parametrize("size,entry,against", _ROUNDING)
def test_a_floor_stop_resting_at_the_wire_target_is_not_a_skip_warning(
    size: float, entry: float, against: bool
) -> None:
    """A restart after a floor raise, while no fresh quote admits another one."""
    probe = _Polls(target="floor", size=size, entry=entry, resting=None)
    wire = _require_rounding(probe.target, size, against)
    polls = _Polls(target="floor", size=size, entry=entry, resting=wire)
    for _ in range(MAX_CONSECUTIVE_SKIPS + 2):
        assert polls.poll(None) is False
    assert polls.kinds() == [BREAKEVEN_SKIPPED_EVENT]
    assert polls.sent == []


@pytest.mark.parametrize("size,entry,against", _ROUNDING)
def test_rejected_raises_against_a_stop_resting_at_the_wire_target_do_not_warn(
    size: float, entry: float, against: bool
) -> None:
    probe = _Polls(target="entry_offset", size=size, entry=entry, resting=None)
    wire = _require_rounding(probe.target, size, against)
    polls = _Polls(target="entry_offset", size=size, entry=entry, resting=wire)
    for _ in range(MAX_RAISE_ATTEMPTS + 2):
        polls.poll()
    assert polls.kinds() == [_ATTEMPT] * MAX_RAISE_ATTEMPTS
    assert RAISE_EXHAUSTED_EVENT not in polls.kinds()


@pytest.mark.parametrize("size,entry,against", _ROUNDING)
def test_a_stop_one_wire_tick_short_of_the_target_still_warns(
    size: float, entry: float, against: bool
) -> None:
    probe = _Polls(target="floor", size=size, entry=entry, resting=None)
    wire = _require_rounding(probe.target, size, against)
    tick = 0.01 if size > 0.0 else 0.001
    short_of = round(wire - tick if size > 0.0 else wire + tick, 3)
    polls = _Polls(target="floor", size=size, entry=entry, resting=short_of)
    for _ in range(MAX_CONSECUTIVE_SKIPS):
        polls.poll(None)
    assert polls.kinds() == [BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT]


@pytest.mark.parametrize("target", ["entry_offset", "floor"])
def test_already_at_target_spends_no_attempt_and_never_warns(target: str) -> None:
    polls = _Polls(
        target=target,
        size=1.0,
        entry=100.0,
        resting=None,
        outcome=STOP_ALREADY_AT_TARGET,
    )
    for _ in range(MAX_RAISE_ATTEMPTS + 3):
        assert polls.poll(_book(106.0, 106.01)) is False
    assert len(polls.sent) == 1
    assert polls.kinds() == [_ATTEMPT]
    event = polls.events[0]
    assert event["attempt"] == 0
    assert event["raised"] is False and event["already_at_target"] is True
    assert event["trigger_price"] == pytest.approx(polls.target)
    assert RAISE_EXHAUSTED_EVENT not in polls.kinds()


def test_already_at_target_clears_an_earlier_protection_warning() -> None:
    snapshot = {
        "event_type": "cohort_snapshot",
        "payload": {
            "assets": [
                {"symbol": "xyz:CCC", "entry_oid": 41, "position_size_signed": 1.0}
            ]
        },
    }
    exhausted = {
        "event_type": RAISE_EXHAUSTED_EVENT,
        "observed_at_utc": "2026-09-24T18:00:00+00:00",
        "payload": {"symbol": "xyz:CCC", "entry_oid": 41, "attempts": 3},
    }
    at_target = {
        "event_type": _ATTEMPT,
        "observed_at_utc": "2026-09-24T18:05:00+00:00",
        "payload": {
            "symbol": "xyz:CCC",
            "entry_oid": 41,
            "attempt": 0,
            "raised": False,
            "already_at_target": True,
        },
    }
    assert len(protection_warnings([exhausted], snapshot)) == 1
    assert protection_warnings([exhausted, at_target], snapshot) == []
    rejected = {
        **at_target,
        "payload": {**at_target["payload"], "already_at_target": False},
    }
    assert len(protection_warnings([exhausted, rejected], snapshot)) == 1


# --------------------------------------------------------------------------- #
# runner wiring
# --------------------------------------------------------------------------- #


def _runner(engine: Mock) -> tuple[MultiAssetLiveRunner, list[str]]:
    runner = object.__new__(MultiAssetLiveRunner)
    events: list[str] = []
    runner._symbols = ("xyz:CCC",)  # type: ignore[attr-defined]
    runner._engines = {"xyz:CCC": engine}  # type: ignore[attr-defined]
    runner._breakeven_attempts = {}  # type: ignore[attr-defined]
    runner._breakeven_skips = {}  # type: ignore[attr-defined]
    runner._profit_lock_controller = SimpleNamespace(  # type: ignore[attr-defined]
        breakeven_requests=frozenset({"xyz:CCC"})
    )
    runner._telemetry = SimpleNamespace(  # type: ignore[attr-defined]
        emit_breakeven_stop_attempt=lambda event, _payload: events.append(event)
    )
    return runner, events


def _engine(entry_oid: int = 41) -> Mock:
    engine = Mock()
    engine.snapshot = SimpleNamespace(
        entry_oid=entry_oid, stop_oid=77, execution_plan=_plan()
    )
    engine.latest_book = None
    engine.normalize_trigger_price.side_effect = _wire
    return engine


def test_the_runner_compares_the_skip_warning_on_the_engines_wire_grid() -> None:
    engine = _engine()
    runner, events = _runner(engine)
    target = breakeven_target_price(_plan(), 100.0037, 1.0)
    wire = _require_rounding(target, 1.0, True)
    venues = (_Venue(_Position(100.0037, 1.0), (_stop(wire),)),)
    report = IntentRoutingReport((), ())
    for _ in range(MAX_CONSECUTIVE_SKIPS + 2):
        assert runner._raise_breakeven_stops(report, venues, NOW) is False
    assert events == [BREAKEVEN_SKIPPED_EVENT]
    engine.raise_protective_stop.assert_not_called()
    engine.normalize_trigger_price.assert_called_with(pytest.approx(target))


def test_the_runner_treats_an_engine_already_at_target_as_no_mutation() -> None:
    engine = _engine()
    engine.latest_book = _book(106.0, 106.01)
    engine.raise_protective_stop.return_value = STOP_ALREADY_AT_TARGET
    runner, events = _runner(engine)
    venues = (_Venue(_Position(100.0, 1.0), (_stop(101.25),)),)
    report = IntentRoutingReport((), ())
    for _ in range(MAX_RAISE_ATTEMPTS + 2):
        assert runner._raise_breakeven_stops(report, venues, NOW) is False
    assert events == [_ATTEMPT]
    engine.raise_protective_stop.assert_called_once()
