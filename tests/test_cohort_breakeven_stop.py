"""Break-even stop raising is bounded, side-correct and skips closing lifecycles."""

from dataclasses import dataclass

import pytest

from hypervector.live.cohort_adaptive_exit_policy import RETENTION_EXIT_POLICY
from hypervector.live.cohort_breakeven_stop import (
    MAX_RAISE_ATTEMPTS,
    breakeven_trigger_price,
    raise_breakeven_stops,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract

from exit_parameter_fixtures import RETENTION_PARAMETERS

_PLAN = ProviderExecutionContract(
    entry_liquidity="taker_ioc",
    stop_policy="fixed_bps",
    stop_bps=100.0,
    target_policy="none",
    maximum_hold_seconds=86400,
    adaptive_exit_policy=RETENTION_EXIT_POLICY,
    retention_exit=RETENTION_PARAMETERS,
).bind(strategy_id="test_breakout_1m", stop_anchor=None)


@dataclass
class _Position:
    entry_price: float | None
    size_signed: float


@dataclass
class _Venue:
    position: _Position


@dataclass
class _Action:
    symbol: str
    action: str


def test_trigger_sits_beyond_entry_on_the_favorable_side() -> None:
    assert breakeven_trigger_price(100.0, 1.0, 25.0) == pytest.approx(100.25)
    assert breakeven_trigger_price(100.0, -1.0, 25.0) == pytest.approx(99.75)
    with pytest.raises(ValueError):
        breakeven_trigger_price(100.0, 0.0, 25.0)


def test_raise_is_attempted_at_most_three_times_then_stops_after_success() -> None:
    calls: list[tuple[str, float]] = []
    events: list[dict[str, object]] = []
    outcomes = iter([False, False, True, True])

    def raise_stop(symbol: str, trigger: float) -> bool:
        calls.append((symbol, trigger))
        return next(outcomes)

    attempts: dict[tuple[str, int], int] = {}
    common = dict(
        requests=frozenset({"SOL"}),
        closed_symbols=set(),
        symbols=("SOL", "ETH"),
        venues={
            "SOL": _Venue(_Position(100.0, 2.0)),
            "ETH": _Venue(_Position(50.0, -1.0)),
        },
        raise_stop=raise_stop,
        attempts=attempts,
        lifecycle_oids={"SOL": 7, "ETH": 9},
        emit=lambda event, payload: events.append({"event": event, **payload}),
        plans={"SOL": _PLAN, "ETH": _PLAN},
    )
    assert raise_breakeven_stops(**common) is False
    assert raise_breakeven_stops(**common) is False
    assert raise_breakeven_stops(**common) is True
    assert raise_breakeven_stops(**common) is False
    assert calls == [("SOL", pytest.approx(100.25))] * 3
    assert attempts[("SOL", 7)] == MAX_RAISE_ATTEMPTS
    assert [e["raised"] for e in events] == [False, False, True]


def test_closing_and_unrequested_symbols_are_skipped() -> None:
    calls: list[str] = []
    assert (
        raise_breakeven_stops(
            requests=frozenset({"SOL", "ETH"}),
            closed_symbols={"SOL"},
            symbols=("SOL", "ETH", "BTC"),
            venues={
                "SOL": _Venue(_Position(100.0, 1.0)),
                "ETH": _Venue(_Position(None, -1.0)),
                "BTC": _Venue(_Position(10.0, 1.0)),
            },
            raise_stop=lambda symbol, trigger: calls.append(symbol) or True,
            attempts={},
            lifecycle_oids={"SOL": 7, "ETH": 9, "BTC": 3},
            emit=lambda event, payload: None,
            plans={"SOL": _PLAN, "ETH": _PLAN, "BTC": _PLAN},
        )
        is False
    )
    assert calls == []


def test_lifecycle_without_retention_parameters_is_not_raised() -> None:
    """A break-even target needs the retention table that defines its offset."""
    calls: list[str] = []
    assert (
        raise_breakeven_stops(
            requests=frozenset({"SOL"}),
            closed_symbols=set(),
            symbols=("SOL",),
            venues={"SOL": _Venue(_Position(100.0, 1.0))},
            raise_stop=lambda symbol, trigger: calls.append(symbol) or True,
            attempts={},
            lifecycle_oids={"SOL": 7},
            emit=lambda event, payload: None,
            plans={"SOL": None},
        )
        is False
    )
    assert calls == []


def test_trigger_offset_comes_from_the_profile_value() -> None:
    assert breakeven_trigger_price(100.0, 1.0, 40.0) == pytest.approx(100.4)
    with pytest.raises(ValueError):
        breakeven_trigger_price(100.0, 1.0, -1.0)
