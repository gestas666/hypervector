"""Opt-in venue stop raise to the v2 software floor, market-guarded and alerting."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_multi_asset_cohort_telemetry import _telemetry

from hypervector.live.cohort_adaptive_exit_policy import (
    ADAPTIVE_EXIT_POLICY,
    RETENTION_EXIT_POLICY,
)
from hypervector.live.cohort_breakeven_stop import (
    BREAKEVEN_SKIPPED_EVENT,
    MAX_RAISE_ATTEMPTS,
    RAISE_EXHAUSTED_EVENT,
    breakeven_target_price,
    raise_breakeven_stops,
)
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
    ProviderExecutionContract,
)
from hypervector.live.cohort_profile_stage import _toml
from hypervector.live.bidirectional_intents import IntentRoutingReport
from hypervector.live.hyperliquid_protocol import (
    SolBookLevel,
    SolBookSnapshot,
    SolOpenOrder,
)
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.sol_range_onset_ledger import SOL_LIVE_EVENT_TYPES
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)
from exit_parameter_fixtures import RETENTION_PARAMETERS

EXIT_POLICY_V2 = "tests/fixtures/profiles/exit_policy_v2.toml"
NOW = 1_800_000_000_000


@dataclass
class _Position:
    entry_price: float | None
    size_signed: float


@dataclass
class _Venue:
    position: _Position
    open_orders: tuple[SolOpenOrder, ...] = field(default_factory=tuple)


def _stop(trigger: float, oid: int = 77) -> SolOpenOrder:
    return SolOpenOrder(oid, 1.0, 1.0, "A", True, True, trigger, "Stop Market", NOW)


def _contract(
    target: str = "floor", stop_bps: float = 250.0
) -> ProviderExecutionContract:
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=stop_bps,
        target_policy="none",
        maximum_hold_seconds=86400,
        adaptive_exit_policy=RETENTION_EXIT_POLICY, retention_exit=RETENTION_PARAMETERS,
        breakeven_stop_target=target,  # type: ignore[arg-type]
    )


def _plan(target: str = "floor", stop_bps: float = 250.0) -> BoundExecutionPlan:
    return _contract(target, stop_bps).bind(
        strategy_id="test_channel_provider", stop_anchor=None
    )


def _book(bid: float, ask: float, stamp: int = NOW - 1_000) -> SolBookSnapshot:
    return SolBookSnapshot(
        stamp,
        (SolBookLevel(bid, 10, 1),),
        (SolBookLevel(ask, 10, 1),),
        (bid + ask) / 2,
        (ask - bid) / ((bid + ask) / 2) * 10_000,
        10,
        10,
        0,
    )


def _run(
    *,
    plan: BoundExecutionPlan,
    size: float,
    book: SolBookSnapshot | None,
    outcomes: list[bool] | None = None,
    attempts: dict[tuple[str, int], int] | None = None,
    resting: SolOpenOrder | None = None,
) -> tuple[bool, list[float], list[dict[str, object]], dict[tuple[str, int], int]]:
    calls: list[float] = []
    events: list[dict[str, object]] = []
    results = iter(outcomes or [True])
    counts = {} if attempts is None else attempts

    def emit(event: str, payload: Mapping[str, object]) -> None:
        events.append({"event": event, **payload})

    mutated = raise_breakeven_stops(
        requests=frozenset({"xyz:CCC"}),
        closed_symbols=set(),
        symbols=("xyz:CCC",),
        venues={
            "xyz:CCC": _Venue(
                _Position(100.0, size), () if resting is None else (resting,)
            )
        },
        raise_stop=lambda symbol, trigger: calls.append(trigger) or next(results),
        attempts=counts,
        lifecycle_oids={"xyz:CCC": 41},
        emit=emit,
        plans={"xyz:CCC": plan},
        books={"xyz:CCC": book},
        observed_ms=NOW,
        stop_oids={"xyz:CCC": 77},
    )
    return mutated, calls, events, counts


@pytest.mark.parametrize(
    "stop_bps,size,expected",
    [
        (250.0, 1.0, 101.25),
        (250.0, -1.0, 98.75),
        (20.0, 1.0, 100.25),
        (20.0, -1.0, 99.75),
        (50.0, 1.0, 100.25),
    ],
)
def test_floor_target_is_the_more_protective_of_offset_and_half_r(
    stop_bps: float, size: float, expected: float
) -> None:
    plan = _plan("floor", stop_bps)
    assert breakeven_target_price(plan, 100.0, size) == pytest.approx(expected)
    offset = _plan("entry_offset", stop_bps)
    assert breakeven_target_price(offset, 100.0, size) == pytest.approx(
        100.25 if size > 0 else 99.75
    )


def test_structural_floor_uses_the_lifecycle_initial_stop_distance() -> None:
    plan = replace(
        _contract(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20.0,
        maximum_stop_bps=250.0,
    ).bind(strategy_id="test", stop_anchor=98.5)
    # R = 150 bps from the anchor, so the floor sits at +75 bps of entry.
    assert breakeven_target_price(plan, 100.0, 2.0) == pytest.approx(100.75)


@pytest.mark.parametrize(
    "size,book,trigger",
    [(1.0, _book(106.0, 106.01), 101.25), (-1.0, _book(93.99, 94.0), 98.75)],
)
def test_floor_mode_raises_to_half_r_inside_the_market(
    size: float, book: SolBookSnapshot, trigger: float
) -> None:
    mutated, calls, events, counts = _run(plan=_plan(), size=size, book=book)
    assert mutated is True
    assert calls == [pytest.approx(trigger)]
    assert counts[("xyz:CCC", 41)] == MAX_RAISE_ATTEMPTS
    assert events == [
        {
            "event": "breakeven_stop_attempt",
            "symbol": "xyz:CCC",
            "entry_oid": 41,
            "attempt": 1,
            "trigger_price": pytest.approx(trigger),
            "raised": True,
            "breakeven_stop_target": "floor",
            "executable_price": book.bids[0].price if size > 0 else book.asks[0].price,
        }
    ]


@pytest.mark.parametrize(
    "size,book",
    [
        (1.0, _book(101.0, 101.01)),
        (1.0, _book(101.25, 101.26)),
        (-1.0, _book(98.74, 98.75)),
        (-1.0, _book(98.0, 99.5)),
    ],
)
def test_target_at_or_through_the_executable_quote_is_skipped_and_journaled(
    size: float, book: SolBookSnapshot
) -> None:
    mutated, calls, events, counts = _run(plan=_plan(), size=size, book=book)
    assert mutated is False and calls == [] and counts == {}
    assert len(events) == 1
    assert events[0]["event"] == BREAKEVEN_SKIPPED_EVENT
    assert events[0]["reason"] == "target_not_protective_of_market"
    assert events[0]["entry_oid"] == 41
    assert events[0]["trigger_price"] == pytest.approx(101.25 if size > 0 else 98.75)


@pytest.mark.parametrize(
    "book",
    [
        None,
        _book(106.0, 106.01, stamp=NOW - 31_000),
        _book(106.0, 106.01, stamp=NOW + 1_000),
        _book(106.0, 105.0),
    ],
)
def test_missing_stale_or_crossed_quote_skips_without_consuming_an_attempt(
    book: SolBookSnapshot | None,
) -> None:
    mutated, calls, events, counts = _run(plan=_plan(), size=1.0, book=book)
    assert mutated is False and calls == [] and counts == {}
    assert [event["reason"] for event in events] == ["executable_quote_unavailable"]
    assert events[0]["executable_price"] is None


def test_entry_offset_default_is_the_exact_baseline_attempt() -> None:
    mutated, calls, events, counts = _run(
        plan=_plan("entry_offset"), size=1.0, book=_book(100.1, 100.11)
    )
    assert mutated is True
    assert calls == [pytest.approx(100.25)]
    assert events == [
        {
            "event": "breakeven_stop_attempt",
            "symbol": "xyz:CCC",
            "entry_oid": 41,
            "attempt": 1,
            "trigger_price": pytest.approx(100.25),
            "raised": True,
        }
    ]


@pytest.mark.parametrize("target", ["entry_offset", "floor"])
def test_exhausted_raise_is_journaled_once_per_lifecycle(target: str) -> None:
    counts: dict[tuple[str, int], int] = {}
    journal: list[dict[str, object]] = []
    for _ in range(MAX_RAISE_ATTEMPTS + 2):
        _, _, events, _ = _run(
            plan=_plan(target),
            size=1.0,
            book=_book(106.0, 106.01),
            outcomes=[False],
            attempts=counts,
        )
        journal.extend(events)
    attempts = [e for e in journal if e["event"] == "breakeven_stop_attempt"]
    exhausted = [e for e in journal if e["event"] == RAISE_EXHAUSTED_EVENT]
    assert len(attempts) == MAX_RAISE_ATTEMPTS
    assert exhausted == [
        {
            "event": RAISE_EXHAUSTED_EVENT,
            "symbol": "xyz:CCC",
            "strategy_id": "test_channel_provider",
            "entry_oid": 41,
            "reason": "protective_stop_raise_exhausted",
            "attempts": MAX_RAISE_ATTEMPTS,
            "trigger_price": pytest.approx(101.25 if target == "floor" else 100.25),
            "breakeven_stop_target": target,
        }
    ]
    assert journal.index(exhausted[0]) == journal.index(attempts[-1]) + 1


def test_new_break_even_events_are_durable_ledger_types() -> None:
    assert {BREAKEVEN_SKIPPED_EVENT, RAISE_EXHAUSTED_EVENT} <= SOL_LIVE_EVENT_TYPES


def test_contract_option_is_typed_opt_in_and_omitted_by_default() -> None:
    default = _contract("entry_offset")
    assert "breakeven_stop_target" not in default.as_payload()
    assert (
        "breakeven_stop_target"
        not in default.bind(strategy_id="x", stop_anchor=None).as_payload()
    )
    floor = _contract("floor")
    assert floor.as_payload()["breakeven_stop_target"] == "floor"
    assert ProviderExecutionContract.from_payload(floor.as_payload()) == floor
    plan = floor.bind(strategy_id="x", stop_anchor=None)
    assert plan.breakeven_stop_target == "floor"
    assert BoundExecutionPlan.from_payload(plan.as_payload()) == plan
    legacy = {
        key: value
        for key, value in default.as_payload().items()
        if key != "breakeven_stop_target"
    }
    assert ProviderExecutionContract.from_payload(legacy) == default


@pytest.mark.parametrize(
    "changes",
    [
        {"breakeven_stop_target": "entry"},
        {"breakeven_stop_target": ""},
        {"adaptive_exit_policy": "none"},
        {"adaptive_exit_policy": ADAPTIVE_EXIT_POLICY},
    ],
)
def test_floor_target_requires_a_known_value_and_the_v2_floor(
    changes: dict[str, str],
) -> None:
    with pytest.raises(CohortExecutionPlanError):
        replace(_contract("floor"), **changes)  # type: ignore[arg-type]


def test_option_absent_keeps_baseline_identity_and_floor_changes_it(tmp_path) -> None:
    config = load_multi_asset_live_config(EXIT_POLICY_V2, mode="observe")
    assert (
        config.profile_fingerprint
        == "4a7c74b468c7a2466a0d3b3150ce1b05db8e4ec0c70ee8f9453e1a78496f42be"
    )
    assert all(
        provider.execution.breakeven_stop_target == "entry_offset"
        for provider in config.providers
    )
    first = config.providers[0]
    changed = replace(
        first, execution=replace(first.execution, breakeven_stop_target="floor")
    )
    candidate = replace(
        config, providers=(changed, *config.providers[1:]), transition_approval=None
    )
    baseline = replace(config, transition_approval=None)
    assert candidate.profile_fingerprint != baseline.profile_fingerprint
    target = tmp_path / "floor.toml"
    target.write_text(_toml(candidate))
    loaded = load_multi_asset_live_config(target, mode="observe")
    assert loaded.profile_fingerprint == candidate.profile_fingerprint
    assert loaded.providers[0].execution.breakeven_stop_target == "floor"
    evidence = provider_exit_policy_evidence(provider_exit_expectation(loaded))
    assert evidence[first.strategy_id]["breakeven_stop_target"] == "floor"
    others = [value for key, value in evidence.items() if key != first.strategy_id]
    assert all("breakeven_stop_target" not in value for value in others)


@pytest.mark.parametrize(
    "resting,warned",
    [(_stop(101.25), False), (_stop(101.3), False), (_stop(97.5), True)],
)
def test_restart_retry_against_an_already_raised_stop_is_not_a_warning(
    resting: SolOpenOrder, warned: bool
) -> None:
    counts: dict[tuple[str, int], int] = {}
    journal: list[dict[str, object]] = []
    for _ in range(MAX_RAISE_ATTEMPTS):
        _, _, events, _ = _run(
            plan=_plan(),
            size=1.0,
            book=_book(106.0, 106.01),
            outcomes=[False],
            attempts=counts,
            resting=resting,
        )
        journal.extend(events)
    exhausted = [e for e in journal if e["event"] == RAISE_EXHAUSTED_EVENT]
    assert len(exhausted) == int(warned)
    assert counts[("xyz:CCC", 41)] == MAX_RAISE_ATTEMPTS


def test_runner_binds_the_lifecycle_plan_cycle_book_and_owned_stop() -> None:
    runner = object.__new__(MultiAssetLiveRunner)
    engine = Mock()
    engine.snapshot = SimpleNamespace(entry_oid=41, stop_oid=77, execution_plan=_plan())
    engine.latest_book = _book(101.1, 101.11)
    engine.raise_protective_stop.return_value = True
    events: list[tuple[str, dict[str, object]]] = []
    runner._symbols = ("xyz:CCC",)
    runner._engines = {"xyz:CCC": engine}
    runner._breakeven_attempts = {}
    runner._breakeven_skips = {}
    runner._profit_lock_controller = SimpleNamespace(
        breakeven_requests=frozenset({"xyz:CCC"})
    )
    runner._telemetry = SimpleNamespace(
        emit_breakeven_stop_attempt=lambda event, payload: events.append(
            (event, dict(payload))
        )
    )
    venues = (_Venue(_Position(100.0, 1.0), (_stop(97.5),)),)
    report = IntentRoutingReport((), ())
    assert runner._raise_breakeven_stops(report, venues, NOW) is False
    assert [event for event, _ in events] == [BREAKEVEN_SKIPPED_EVENT]
    engine.raise_protective_stop.assert_not_called()
    engine.latest_book = _book(106.0, 106.01)
    assert runner._raise_breakeven_stops(report, venues, NOW) is True
    engine.raise_protective_stop.assert_called_once_with(
        trigger_price=pytest.approx(101.25)
    )


def test_cohort_telemetry_journals_skip_and_exhaustion_but_nothing_else(
    tmp_path,
) -> None:
    telemetry, ledger = _telemetry(tmp_path)
    telemetry.emit_breakeven_stop_attempt(
        BREAKEVEN_SKIPPED_EVENT,
        {"symbol": "SOL", "entry_oid": 7, "reason": "executable_quote_unavailable"},
    )
    telemetry.emit_breakeven_stop_attempt(
        RAISE_EXHAUSTED_EVENT,
        {"symbol": "SOL", "entry_oid": 7, "reason": RAISE_EXHAUSTED_EVENT},
    )
    with pytest.raises(ValueError, match="break-even"):
        telemetry.emit_breakeven_stop_attempt("protective_stop_raised", {})
    rows = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    assert [row["event_type"] for row in rows[-2:]] == [
        BREAKEVEN_SKIPPED_EVENT,
        RAISE_EXHAUSTED_EVENT,
    ]
