"""Submission-boundary freshness regressions for automatic cohort entries."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from test_multi_asset_live_runner import (
    _SYMBOLS,
    _contract,
    _Engine,
    _Poller,
    _router,
    _Telemetry,
)

from hypervector.live.bidirectional_intents import RoutingAction, StrategyIntent
from hypervector.live.cohort_entry_submission import (
    entry_delays_from_providers,
    execute_fresh_routed_actions,
    stale_entry_before_submission,
)
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_range_onset_engine_contract import SolEntryNotFilledError


class _ThirtySecondPoller(_Poller):
    def maximum_entry_delay_ms(self, strategy_id: str, symbol: str) -> int:
        """Return the frozen provider-symbol entry-age ceiling."""
        assert strategy_id == "hulk"
        assert symbol == "BTC"
        return 30_000


@dataclass(frozen=True)
class _Provider:
    strategy_id: str
    symbols: tuple[str, ...]
    execution_symbols: tuple[str, ...]
    maximum_entry_delay_seconds: int


def test_entry_delay_projection_excludes_observe_only_symbols() -> None:
    """Submission policy must cover executable routes without widening authority."""
    provider = _Provider("index", ("xyz:AAA", "xyz:BBB"), ("xyz:AAA",), 30)

    assert entry_delays_from_providers((provider,)) == {("index", "xyz:AAA"): 30_000}


def test_entry_at_exact_submission_deadline_remains_executable() -> None:
    """The final guard preserves the existing strict-greater-than contract."""
    action = RoutingAction("enter", "hulk", "BTC", "long", 1_000, 100.0)

    assert (
        stale_entry_before_submission(
            action,
            observed_ms=31_000,
            delays={("hulk", "BTC"): 30_000},
        )
        is None
    )


def test_fresh_entry_serializes_exact_submission_boundary_evidence() -> None:
    """An accepted entry must retain the final clock and route limit."""
    action = RoutingAction("enter", "hulk", "BTC", "long", 1_000, 100.0)
    executed: list[RoutingAction] = []

    submitted, withheld = execute_fresh_routed_actions(
        (action,),
        now_ms=lambda: 31_000,
        delays={("hulk", "BTC"): 30_000},
        execute=lambda action, _: executed.append(action),
    )

    assert withheld == ()
    assert executed == list(submitted)
    assert submitted[0].submission_observed_at_ms == 31_000
    assert submitted[0].submission_age_ms == 30_000
    assert submitted[0].submission_limit_ms == 30_000


def test_ioc_no_fill_is_reported_and_does_not_abort_later_actions() -> None:
    """A definitive flat IOC no-fill must not terminate the cohort cycle."""
    first = RoutingAction("enter", "ltc", "LTC", "long", 1_000, 100.0)
    second = RoutingAction("enter", "hulk", "BTC", "short", 1_000, 100.0)
    attempted: list[RoutingAction] = []

    def execute(
        action: RoutingAction, _deadline: EntrySubmissionDeadline | None
    ) -> None:
        attempted.append(action)
        if action.symbol == "LTC":
            raise SolEntryNotFilledError("IOC entry not filled")

    submitted, withheld = execute_fresh_routed_actions(
        (first, second),
        now_ms=lambda: 2_000,
        delays={("ltc", "LTC"): 30_000, ("hulk", "BTC"): 30_000},
        execute=execute,
    )

    assert [row.symbol for row in attempted] == ["LTC", "BTC"]
    assert [row.symbol for row in submitted] == ["BTC"]
    assert [(row.intent.symbol, row.reason) for row in withheld] == [
        ("LTC", "entry_ioc_no_fill")
    ]


def test_stale_entry_serializes_exact_non_submission_evidence() -> None:
    """A stale entry must report the clock evidence that prevented submission."""
    action = RoutingAction("enter", "hulk", "BTC", "long", 1_000, 100.0)

    withheld = stale_entry_before_submission(
        action,
        observed_ms=31_001,
        delays={("hulk", "BTC"): 30_000},
    )

    assert withheld is not None
    assert withheld.submission_observed_at_ms == 31_001
    assert withheld.submission_age_ms == 30_001
    assert withheld.submission_limit_ms == 30_000


def test_submission_guard_never_withholds_an_automatic_close() -> None:
    """Entry freshness cannot delay a selected automatic exit."""
    action = RoutingAction("close", "hulk", "BTC", "long", 1_000, 100.0)
    executed: list[RoutingAction] = []

    def unexpected_clock_read() -> int:
        raise AssertionError("automatic closes must not sample entry-age time")

    submitted, withheld = execute_fresh_routed_actions(
        (action,),
        now_ms=unexpected_clock_read,
        delays={("hulk", "BTC"): 30_000},
        execute=lambda action, _: executed.append(action),
    )

    assert submitted == (action,)
    assert withheld == ()
    assert executed == [action]


def test_automatic_entry_is_rechecked_immediately_before_submission(
    tmp_path: Path,
) -> None:
    """Cycle work cannot push a previously fresh entry beyond its deadline."""
    decision = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    clock = iter(
        (
            decision.replace(second=25),
            decision.replace(second=25),
            decision.replace(second=31),
        )
    )
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    telemetry = _Telemetry()
    intent = StrategyIntent(
        "hulk", "BTC", "long", int(decision.timestamp() * 1_000), 100.0, "signal"
    )
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_ThirtySecondPoller((intent,)),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: next(clock),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={("hulk", "BTC"): 30_000},
        executable_provider_symbols=frozenset({("hulk", "BTC")}),
    )

    runner.start(activation_time_ms=int(decision.timestamp() * 1_000))
    runner.poll_once()

    assert engines["BTC"].entries == []
    report = telemetry.routings[0][1]
    assert report.actions == ()
    assert [(row.intent.symbol, row.reason) for row in report.withheld] == [
        ("BTC", "stale_before_submission")
    ]
