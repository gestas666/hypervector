"""Deterministic orchestration tests for the shared multi-asset live backend."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hyperliquid.utils.error import ServerError

from multi_asset_live_runner_fixtures import (
    execution_contract as _contract,
)
from multi_asset_live_runner_fixtures import (
    venue_snapshot as _venue,
)

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_funding_window import CohortFundingWindow
from hypervector.live.cohort_runtime_fault import runtime_failure_stage
from hypervector.live.cohort_operator_commands import (
    CohortOperatorClaim,
    CohortOperatorCommand,
)
from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import (
    CohortIntentPoll,
    CohortMarketBar,
)
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


class _Engine:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.current = SolLiveSnapshot()
        self.entries: list[tuple[str, float, int]] = []
        self.entry_sizing: list[CohortEntrySizing | None] = []
        self.exits: list[tuple[float, str]] = []
        self.decisions: list[dict[str, object]] = []
        self.reconciliations: list[tuple[int, int]] = []

    @property
    def snapshot(self) -> SolLiveSnapshot:
        return self.current

    def start(self) -> SolLiveSnapshot:
        self.current = SolLiveSnapshot(state=SolLiveState.FLAT)
        return self.current

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        self.reconciliations.append((funding_start_time_ms, funding_end_time_ms))
        return _venue(self.current.position_size_signed)

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        self.decisions.append(payload)

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
        entry_sizing: CohortEntrySizing | None = None,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> SolLiveSnapshot:
        assert decision_time_ms is not None
        if entry_deadline is not None:
            entry_deadline.check("adapter_dispatch")
        size = 1.0 if side == "long" else -1.0
        self.entries.append((side, mark_price, decision_time_ms))
        self.entry_sizing.append(entry_sizing)
        self.current = SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=1,
            stop_oid=2,
            position_size_signed=size,
            opened_at_ms=decision_time_ms,
        )
        return self.current

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        self.exits.append((mark_price, reason))
        self.current = SolLiveSnapshot(state=SolLiveState.FLAT)
        return self.current

    def stop(self, reason: str) -> SolLiveSnapshot:
        self.current = replace(
            self.current,
            state=SolLiveState.STOPPED,
            stop_reason=reason,
        )
        return self.current


class _Poller:
    def __init__(
        self,
        intents: tuple[StrategyIntent, ...],
        evaluations: tuple[ProviderEvaluation, ...] = (),
        regime_evaluations: tuple[ProviderEvaluation, ...] = (),
    ) -> None:
        self.intents = intents
        self.evaluations = evaluations
        self.regime_evaluations = regime_evaluations
        self.activations: list[int] = []
        self.observed_at: list[datetime] = []

    def activate(self, activation_time_ms: int) -> None:
        self.activations.append(activation_time_ms)

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        self.observed_at.append(observed_at)
        return CohortIntentPoll(
            intents=self.intents,
            reference_prices={symbol: 100.0 for symbol in _SYMBOLS},
            market_bars={
                symbol: (
                    CohortMarketBar(
                        symbol,
                        1_785_585_540_000,
                        99.0,
                        101.0,
                        98.0,
                        100.0,
                        10.0,
                    ),
                )
                for symbol in _SYMBOLS
            },
            evaluations=self.evaluations,
            regime_evaluations=self.regime_evaluations,
        )


class _Telemetry:
    def __init__(self, transition_drain: CohortTransitionDrain | None = None) -> None:
        self.configurations = 0
        self.routings: list[object] = []
        self.canonical_regimes: list[object] = []
        self.snapshots: list[object] = []
        self.market_bars: list[object] = []
        self.heartbeats = 0
        self.degraded_polls: list[tuple[str, str]] = []
        self.operator_events: list[dict[str, object]] = []
        self.maximum_hold_events: list[dict[str, object]] = []
        self.provider_exit_events: list[dict[str, object]] = []
        self.profit_lock_events: list[dict[str, object]] = []
        self.funding_windows: list[dict[str, object]] = []
        self.transition_drain = transition_drain
        self.transition_states: list[str] = []

    def emit_configuration(self) -> None:
        self.configurations += 1

    def emit_routing(
        self,
        intents: object,
        report: object,
        evaluations: object,
    ) -> None:
        self.routings.append((intents, report, evaluations))

    def emit_canonical_regimes(self, evaluations: object) -> None:
        self.canonical_regimes.append(evaluations)

    def emit_snapshot(self, *, account: object, assets: object) -> None:
        self.snapshots.append((account, assets))
        if self.transition_drain is not None:
            self.transition_states.append(
                str(self.transition_drain.as_payload()["status"])
            )

    def emit_market_bars(self, bars: object) -> None:
        self.market_bars.append(bars)

    def emit_heartbeat(self) -> None:
        self.heartbeats += 1

    def emit_funding_reconciliation_window(self, window: CohortFundingWindow) -> None:
        self.funding_windows.append(window.as_payload())

    def emit_poll_degraded(self, *, source: str, reason: str) -> None:
        self.degraded_polls.append((source, reason))

    def emit_operator_command(self, payload: dict[str, object]) -> None:
        self.operator_events.append(payload)

    def recorded_maximum_hold_decision(
        self, decision_id: str
    ) -> dict[str, object] | None:
        return next(
            (
                dict(event)
                for event in self.maximum_hold_events
                if event.get("decision_id") == decision_id
            ),
            None,
        )

    def emit_maximum_hold_decision(self, payload: dict[str, object]) -> None:
        self.maximum_hold_events.append(payload)

    def recorded_provider_exit_decision(
        self, decision_id: str
    ) -> dict[str, object] | None:
        return next(
            (
                dict(event)
                for event in self.provider_exit_events
                if event.get("decision_id") == decision_id
            ),
            None,
        )

    def emit_provider_exit_decision(self, payload: dict[str, object]) -> None:
        self.provider_exit_events.append(payload)

    def recorded_profit_lock_decision(
        self, decision_id: str
    ) -> dict[str, object] | None:
        return next(
            (
                dict(event)
                for event in self.profit_lock_events
                if event.get("decision_id") == decision_id
            ),
            None,
        )

    def emit_profit_lock_decision(self, payload: dict[str, object]) -> None:
        self.profit_lock_events.append(payload)


class _Commands:
    def __init__(self, *commands: CohortOperatorCommand) -> None:
        self.claims = tuple(
            CohortOperatorClaim(
                command.request_id, Path(command.request_id), command, None
            )
            for command in commands
        )
        self.outcomes: list[tuple[str, str, str]] = []

    def claim_pending(self) -> tuple[CohortOperatorClaim, ...]:
        claims, self.claims = self.claims, ()
        return claims

    def finalize(
        self,
        claim: CohortOperatorClaim,
        *,
        status: str,
        reason: str,
    ) -> None:
        self.outcomes.append((claim.request_id, status, reason))


def _intent(symbol: str, side: str) -> StrategyIntent:
    return StrategyIntent(
        "hulk",
        symbol,
        side,
        1_785_585_600_000,
        100.0,
        "signal",
    )


def _router() -> BidirectionalIntentRouter:
    capabilities = tuple(
        StrategyCapability("hulk", symbol, frozenset({"long", "short"}), 10)
        for symbol in _SYMBOLS
    )
    return BidirectionalIntentRouter(capabilities, maximum_positions=2)


def _runner(
    tmp_path: Path,
    intents: tuple[StrategyIntent, ...],
    *,
    maximum_hold_seconds_by_symbol: dict[str, int] | None = None,
    execution_contracts: dict[str, ProviderExecutionContract] | None = None,
    executable_provider_symbols: frozenset[tuple[str, str]] | None = None,
    executable_provider_directions: frozenset[tuple[str, str, str]] | None = None,
    provider_entry_sizing: dict[tuple[str, str], CohortEntrySizing] | None = None,
    provider_directional_entry_sizing: dict[tuple[str, str, str], CohortEntrySizing]
    | None = None,
    operator_commands: _Commands | None = None,
    transition_drain: CohortTransitionDrain | None = None,
    evaluations: tuple[ProviderEvaluation, ...] = (),
    regime_evaluations: tuple[ProviderEvaluation, ...] = (),
) -> tuple[MultiAssetLiveRunner, dict[str, _Engine], _Telemetry]:
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    telemetry = _Telemetry(transition_drain)
    executable_pairs = executable_provider_symbols or frozenset(
        ("hulk", symbol) for symbol in _SYMBOLS
    )
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_Poller(intents, evaluations, regime_evaluations),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol=(
            maximum_hold_seconds_by_symbol
            if maximum_hold_seconds_by_symbol is not None
            else {symbol: 28_800 for symbol in _SYMBOLS}
        ),
        execution_contracts=(
            execution_contracts
            if execution_contracts is not None
            else {"hulk": _contract()}
        ),
        maximum_entry_delay_ms_by_provider_symbol={
            pair: 60_000 for pair in executable_pairs
        },
        executable_provider_symbols=executable_pairs,
        executable_provider_directions=executable_provider_directions,
        provider_entry_sizing=provider_entry_sizing or {},
        provider_directional_entry_sizing=provider_directional_entry_sizing or {},
        operator_commands=operator_commands,
        transition_drain=transition_drain,
    )
    return runner, engines, telemetry


def test_runner_persists_canonical_regime_outside_provider_routing_rows(
    tmp_path: Path,
) -> None:
    """The backend journals detector state without treating it as a setup route."""
    canonical = _regime_evaluation(
        "canonical_regime_telemetry_v1",
        "BTC",
        1_785_600_000_000,
    )
    runner, _, telemetry = _runner(
        tmp_path,
        (),
        regime_evaluations=(canonical,),
    )

    runner.run(max_polls=1)

    assert telemetry.canonical_regimes == [(canonical,)]
    assert telemetry.routings[0][2] == ()


def _operator(action: str, symbol: str, *, side: str | None) -> CohortOperatorCommand:
    provider = "hulk" if action == "manual_enter" else None
    return CohortOperatorCommand(
        request_id=("a" if action == "manual_enter" else "b") * 32,
        run_id="fixture-run",
        profile_fingerprint="c" * 64,
        created_at_utc="2026-08-01T12:00:00+00:00",
        action=action,
        symbol=symbol,
        provider=provider,
        side=side,
        settings=None,
    )


def test_manual_entry_uses_backend_risk_path_and_suppresses_strategy_reentry(
    tmp_path: Path,
) -> None:
    """An override enters through the engine and blocks same-cycle auto action."""
    commands = _Commands(_operator("manual_enter", "BTC", side="long"))
    sizing = CohortEntrySizing(0.06, 20.0)
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "short"),),
        operator_commands=commands,
        provider_entry_sizing={("hulk", "BTC"): sizing},
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries == [("long", 100.0, 1_785_585_600_000)]
    assert engines["BTC"].entry_sizing == [sizing]
    assert engines["BTC"].decisions[0]["execution_plan"]["strategy_id"] == (
        "operator_override:hulk"
    )
    assert engines["BTC"].decisions[0]["entry_sizing"] == sizing.as_payload()
    assert engines["BTC"].exits == []
    assert commands.outcomes == [("a" * 32, "completed", "venue lifecycle reconciled")]
    assert [event["status"] for event in telemetry.operator_events] == [
        "received",
        "accepted",
        "completed",
    ]
    assert telemetry.routings[0][1].withheld[0].reason == "operator_action_this_cycle"
    assert telemetry.funding_windows[0]["post_action_reconciliation"] is True
    assert telemetry.funding_windows[0]["action_count"] == 1


def test_manual_entry_rejects_a_side_without_directional_authority(
    tmp_path: Path,
) -> None:
    """Provider-symbol authority cannot be widened by a manual side request."""
    commands = _Commands(_operator("manual_enter", "BTC", side="short"))
    runner, engines, telemetry = _runner(
        tmp_path,
        (),
        operator_commands=commands,
        executable_provider_directions=frozenset({("hulk", "BTC", "long")}),
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries == []
    assert commands.outcomes == [
        ("a" * 32, "rejected", "provider, symbol, and side lack execution authority")
    ]
    assert [event["status"] for event in telemetry.operator_events] == [
        "received",
        "rejected",
    ]


def test_intent_clock_is_sampled_after_reconciliation(tmp_path: Path) -> None:
    """Same-cycle venue books must precede the intent poller's causal cutoff."""
    before = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    after = datetime(2026, 8, 1, 12, 0, 4, tzinfo=UTC)
    clock = iter((before, after))
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    poller = _Poller(())
    telemetry = _Telemetry()
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: next(clock),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={
            ("hulk", symbol): 60_000 for symbol in _SYMBOLS
        },
        executable_provider_symbols=frozenset(("hulk", symbol) for symbol in _SYMBOLS),
    )

    runner.start(activation_time_ms=int(before.timestamp() * 1_000))
    runner.poll_once()

    assert poller.observed_at == [after]


def test_post_reconcile_intent_clock_does_not_advance_funding_cursor(
    tmp_path: Path,
) -> None:
    """No-action cycles retain the exact funding end used by reconciliation."""
    activation = datetime(2026, 8, 1, 11, 59, 0, tzinfo=UTC)
    before_first = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    after_first = datetime(2026, 8, 1, 12, 0, 4, tzinfo=UTC)
    before_second = datetime(2026, 8, 1, 12, 0, 15, tzinfo=UTC)
    after_second = datetime(2026, 8, 1, 12, 0, 19, tzinfo=UTC)
    clock = iter((before_first, after_first, before_second, after_second))
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    telemetry = _Telemetry()
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_Poller(()),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: next(clock),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={
            ("hulk", symbol): 60_000 for symbol in _SYMBOLS
        },
        executable_provider_symbols=frozenset(("hulk", symbol) for symbol in _SYMBOLS),
    )

    runner.start(activation_time_ms=int(activation.timestamp() * 1_000))
    runner.poll_once()
    runner.poll_once()

    expected = [
        (
            int(activation.timestamp() * 1_000) - 86_400_000,
            int(before_first.timestamp() * 1_000),
        ),
        (
            int(before_first.timestamp() * 1_000),
            int(before_second.timestamp() * 1_000),
        ),
    ]
    assert engines["BTC"].reconciliations == expected
    assert [
        (
            row["funding_start_time_ms"],
            row["committed_funding_end_time_ms"],
            row["next_funding_start_time_ms"],
        )
        for row in telemetry.funding_windows
    ] == [
        (expected[0][0], expected[0][1], expected[0][1]),
        (expected[1][0], expected[1][1], expected[1][1]),
    ]


def test_provider_symbol_sizing_is_bound_to_the_selected_automatic_intent(
    tmp_path: Path,
) -> None:
    """Automatic entries receive only their exact provider-symbol policy."""
    sizing = CohortEntrySizing(0.06, 20.0)
    runner, engines, _ = _runner(
        tmp_path,
        (_intent("SOL", "long"), _intent("HYPE", "short")),
        provider_entry_sizing={("hulk", "SOL"): sizing},
    )

    assert runner.run(max_polls=1) == 1

    assert engines["SOL"].entry_sizing == [sizing]
    assert engines["HYPE"].entry_sizing == [None]
    assert engines["SOL"].decisions[0]["entry_sizing"] == sizing.as_payload()
    assert engines["HYPE"].decisions[0]["entry_sizing"] is None


def test_directional_sizing_precedes_provider_symbol_fallback(tmp_path: Path) -> None:
    """A route can stay bidirectional while sizing each selected side separately."""
    fallback = CohortEntrySizing(0.03, 20.0)
    long_policy = CohortEntrySizing(0.08, 60.0)
    runner, engines, _ = _runner(
        tmp_path,
        (_intent("SOL", "long"), _intent("HYPE", "short")),
        provider_entry_sizing={
            ("hulk", "SOL"): fallback,
            ("hulk", "HYPE"): fallback,
        },
        provider_directional_entry_sizing={
            ("hulk", "SOL", "long"): long_policy,
        },
    )

    assert runner.run(max_polls=1) == 1
    assert engines["SOL"].entry_sizing == [long_policy]
    assert engines["HYPE"].entry_sizing == [fallback]
    assert engines["SOL"].decisions[0]["entry_sizing_source"] == (
        "provider_direction_override"
    )
    assert engines["HYPE"].decisions[0]["entry_sizing_source"] == (
        "provider_symbol_override"
    )


def test_manual_close_is_reduce_only_engine_exit_and_does_not_reenter(
    tmp_path: Path,
) -> None:
    """An override close uses the protected engine exit with explicit attribution."""
    commands = _Commands(_operator("manual_close", "BTC", side=None))
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "long"),),
        operator_commands=commands,
    )
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=-1.0,
        opened_at_ms=1_785_584_600_000,
    )

    runner.start(activation_time_ms=1_785_600_000_000, start_engines=False)
    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "operator_manual_close")]
    assert engines["BTC"].entries == []
    assert (
        telemetry.routings[0][1].actions[0].strategy_id
        == "operator_override:manual_close"
    )


def test_manual_close_suppresses_one_cycle_then_automatic_strategy_resumes(
    tmp_path: Path,
) -> None:
    """A one-off override never changes the portfolio into manual-only mode."""
    commands = _Commands(_operator("manual_close", "BTC", side=None))
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "long"),),
        operator_commands=commands,
    )
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=-1.0,
        opened_at_ms=1_785_584_600_000,
    )

    runner.start(activation_time_ms=1_785_600_000_000, start_engines=False)
    assert runner.poll_once() == 1
    assert engines["BTC"].entries == []

    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "operator_manual_close")]
    assert engines["BTC"].entries == [("long", 100.0, 1_785_585_600_000)]
    assert telemetry.routings[1][1].actions[0].strategy_id == "hulk"


def test_transition_drain_withholds_flat_entries_and_stops_at_clean_boundary(
    tmp_path: Path,
) -> None:
    """A requested transition closes the entry race before stopping flat."""
    drain = CohortTransitionDrain(
        path=tmp_path / "transition_drain.json",
        run_id="fixture-run",
        profile_fingerprint="c" * 64,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    drain.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-01T11:59:59+00:00",
    )
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "long"),),
        transition_drain=drain,
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries == []
    report = telemetry.routings[0][1]
    assert [(item.intent.symbol, item.reason) for item in report.withheld] == [
        ("BTC", "operator_transition_drain")
    ]
    assert drain.snapshot is not None
    assert drain.snapshot.status == "completed"
    assert telemetry.transition_states == ["completed"]
    assert {engine.snapshot.stop_reason for engine in engines.values()} == {
        "operator_transition_drain_complete"
    }


def test_transition_drain_command_dominates_manual_entry_in_same_cycle(
    tmp_path: Path,
) -> None:
    """A drain request is activated before any same-batch opening override."""
    drain = CohortTransitionDrain(
        path=tmp_path / "transition_drain.json",
        run_id="fixture-run",
        profile_fingerprint="c" * 64,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    commands = _Commands(
        _operator("manual_enter", "BTC", side="long"),
        _operator("transition_drain", "MULTI", side=None),
    )
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "long"),),
        operator_commands=commands,
        transition_drain=drain,
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries == []
    assert commands.outcomes == [
        ("b" * 32, "completed", "transition drain activated"),
        ("a" * 32, "rejected", "manual entry is disabled by transition drain"),
    ]
    assert [event["status"] for event in telemetry.operator_events] == [
        "received",
        "accepted",
        "completed",
        "received",
        "rejected",
        "drained",
    ]


def test_transition_drain_allows_opposite_intent_to_close_existing_position(
    tmp_path: Path,
) -> None:
    """Draining blocks openings but preserves strategy-directed exits."""
    drain = CohortTransitionDrain(
        path=tmp_path / "transition_drain.json",
        run_id="fixture-run",
        profile_fingerprint="c" * 64,
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
    )
    drain.activate(
        request_id="e" * 32,
        requested_at_utc="2026-08-01T11:59:59+00:00",
    )
    runner, engines, _ = _runner(
        tmp_path,
        (_intent("BTC", "short"),),
        transition_drain=drain,
    )
    runner.start(activation_time_ms=1_785_600_000_000)
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=1_785_584_600_000,
    )

    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "opposite_strategy_intent")]
    assert engines["BTC"].entries == []
    assert drain.snapshot is not None
    assert drain.snapshot.status == "completed"


def test_one_process_routes_two_coins_and_attributes_capacity(tmp_path: Path) -> None:
    """Two different coins may enter while the third and fourth remain visible."""
    runner, engines, telemetry = _runner(
        tmp_path,
        tuple(
            _intent(symbol, side)
            for symbol, side in zip(
                _SYMBOLS,
                ("long", "short", "long", "short"),
                strict=True,
            )
        ),
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries[0][0] == "long"
    assert engines["ETH"].entries[0][0] == "short"
    assert engines["SOL"].entries == []
    assert engines["HYPE"].entries == []
    report = telemetry.routings[0][1]
    assert [item.reason for item in report.withheld] == [
        "portfolio_position_capacity",
        "portfolio_position_capacity",
    ]
    assert telemetry.routings[0][2] == ()
    assert telemetry.configurations == 1
    assert len(telemetry.market_bars) == 1
    assert set(telemetry.market_bars[0]) == set(_SYMBOLS)
    assert telemetry.heartbeats == 1
    plan = engines["BTC"].decisions[0]["execution_plan"]
    assert isinstance(plan, dict)
    assert plan["strategy_id"] == "hulk"


def test_opposite_intent_closes_without_same_cycle_reversal(tmp_path: Path) -> None:
    """A one-way symbol closes first and waits for a later fresh entry."""
    runner, engines, _ = _runner(tmp_path, (_intent("BTC", "short"),))
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=1_785_584_600_000,
    )

    runner.start(activation_time_ms=1_785_600_000_000, start_engines=False)
    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "opposite_strategy_intent")]
    assert engines["BTC"].entries == []


def test_maximum_hold_closes_at_completed_reference_without_reentry(
    tmp_path: Path,
) -> None:
    """An expired protected position closes once and suppresses same-cycle intents."""
    runner, engines, telemetry = _runner(tmp_path, (_intent("BTC", "long"),))
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=-1.0,
        opened_at_ms=1_785_550_000_000,
    )

    runner.start(activation_time_ms=1_785_600_000_000, start_engines=False)
    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "maximum_hold_seconds")]
    assert engines["BTC"].entries == []
    report = telemetry.routings[0][1]
    assert report.actions[0].strategy_id == "cohort_maximum_hold"
    assert report.withheld[0].reason == "maximum_hold_exit_this_cycle"


def test_open_position_uses_its_persisted_provider_maximum_hold(tmp_path: Path) -> None:
    """Provider hold overrides the legacy symbol fallback after an entry."""
    runner, engines, _ = _runner(tmp_path, ())
    plan = _contract(maximum_hold_seconds=30).bind(
        strategy_id="hulk",
        stop_anchor=None,
    )
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=1_785_585_500_000,
        execution_plan=plan,
    )

    runner.start(activation_time_ms=1_785_600_000_000, start_engines=False)
    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "maximum_hold_seconds")]


def test_bound_provider_recipe_exit_closes_open_lifecycle(tmp_path: Path) -> None:
    """A recipe exit closes only the lifecycle bound to that provider."""
    evaluation = ProviderEvaluation(
        strategy_id="hulk",
        symbol="BTC",
        decision_time_ms=1_785_585_600_000,
        reference_price=100.0,
        decision_action="close_long",
        eligible=False,
        reason="hip3_swing_ha_flip",
        side="long",
        readiness=SignalReadiness(
            "long",
            3,
            4,
            ("heikin_ashi_color_mismatch",),
            ("HA COLOR -1",),
            {"exit_mode": "ha_flip"},
        ),
        exit_sides=frozenset({"long"}),
        exit_reason="hip3_swing_ha_flip",
    )
    runner, engines, telemetry = _runner(tmp_path, (), evaluations=(evaluation,))
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=1_785_584_600_000,
        execution_plan=replace(_contract(), provider_recipe_exit_policy="honor").bind(
            strategy_id="hulk", stop_anchor=None
        ),
    )

    runner.start(activation_time_ms=1_785_585_600_000, start_engines=False)
    assert runner.poll_once() == 1

    assert engines["BTC"].exits == [(100.0, "hip3_swing_ha_flip")]
    assert telemetry.routings[0][1].actions[0].strategy_id == "hulk"
    assert engines["BTC"].decisions[0]["exit_reason"] == "hip3_swing_ha_flip"


def test_supported_soft_deadline_is_journaled_once(tmp_path: Path) -> None:
    """One protected lifecycle emits one causal extension decision."""
    observed_ms = int(datetime(2026, 8, 1, 12, tzinfo=UTC).timestamp() * 1_000)
    opened_at_ms = observed_ms - 28_800_000
    evaluations = (
        _regime_evaluation("hulk", "HYPE", observed_ms),
        _regime_evaluation("test_breakout_1m", "HYPE", observed_ms),
    )
    runner, engines, telemetry = _runner(tmp_path, (), evaluations=evaluations)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=28_800,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_seconds=86_400,
        maximum_hold_evidence_maximum_age_seconds=60,
    ).bind(strategy_id="hulk", stop_anchor=None)
    engines["HYPE"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=99,
        stop_oid=100,
        position_size_signed=1.0,
        opened_at_ms=opened_at_ms,
        execution_plan=plan,
    )

    runner.start(activation_time_ms=observed_ms, start_engines=False)
    runner.poll_once()
    runner.poll_once()

    assert telemetry.maximum_hold_events == [
        {
            "decision_id": "HYPE:99:soft_maximum_hold",
            "decision_stage": "soft",
            "lifecycle_id": "HYPE:99",
            "symbol": "HYPE",
            "strategy_id": "hulk",
            "side": "long",
            "decision_time_ms": observed_ms,
            "opened_at_ms": opened_at_ms,
            "elapsed_ms": 28_800_000,
            "soft_deadline_timestamp_ms": observed_ms,
            "hard_deadline_timestamp_ms": opened_at_ms + 86_400_000,
            "outcome": "extend",
            "exit_reason": None,
            "structure_alignment_score": 1.0,
            "structure_alignment_threshold": 0.5,
            "maximum_hold_evidence_maximum_age_ms": 60_000,
            "provider_evidence_age_ms": 0,
            "canonical_evidence_age_ms": 0,
            "maximum_hold_evidence_status": "fresh",
            "provider_evaluation": evaluations[0].as_payload(),
            "canonical_evaluation": evaluations[1].as_payload(),
        }
    ]


def _regime_evaluation(
    strategy_id: str,
    symbol: str,
    decision_time_ms: int,
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="hold",
        eligible=False,
        reason="test",
        side="long",
        readiness=SignalReadiness("long", 1, 1, (), ("TEST",), {}),
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="TREND_UP",
    )


def test_runner_uses_configured_start_to_start_poll_period(tmp_path: Path) -> None:
    """Cycle work is deducted rather than added to the configured poll period."""
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    sleeps: list[float] = []
    monotonic_values = iter((0.0, 10.0, 15.0))
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_Poller(()),
        telemetry=_Telemetry(),
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: next(monotonic_values),
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={
            ("hulk", symbol): 60_000 for symbol in _SYMBOLS
        },
        executable_provider_symbols=frozenset(("hulk", symbol) for symbol in _SYMBOLS),
    )

    assert runner.run(max_polls=2) == 2
    assert sleeps == [5.0]


def test_profit_lock_candle_gap_remains_the_latest_health_state(tmp_path: Path) -> None:
    """A healthy heartbeat cannot immediately hide a disabled profit-lock path."""
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
        profit_lock_policy="completed_bar_trailing",
        profit_lock_activation_bps=100.0,
        profit_lock_floor_bps=40.0,
        profit_lock_giveback_bps=80.0,
    )
    runner, engines, telemetry = _runner(
        tmp_path,
        (),
        execution_contracts={"hulk": contract},
    )
    runner.start(activation_time_ms=1_785_585_600_000, start_engines=False)
    engines["BTC"].current = SolLiveSnapshot(
        state=SolLiveState.OPEN,
        entry_oid=1,
        stop_oid=2,
        position_size_signed=1.0,
        opened_at_ms=1_785_585_450_000,
        execution_plan=contract.bind(strategy_id="hulk", stop_anchor=None),
    )

    assert runner.poll_once() == 0

    assert telemetry.degraded_polls
    assert telemetry.degraded_polls[-1][0] == "profit_lock_candles"
    assert telemetry.heartbeats == 0


def test_observe_only_provider_symbol_is_journaled_but_not_executed(
    tmp_path: Path,
) -> None:
    """Explicit research pairs remain visible without receiving live authority."""
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("BTC", "long"), _intent("SOL", "short")),
        executable_provider_symbols=frozenset({("hulk", "SOL")}),
    )

    assert runner.run(max_polls=1) == 1

    assert engines["BTC"].entries == []
    assert engines["SOL"].entries[0][0] == "short"
    report = telemetry.routings[0][1]
    assert [(item.intent.symbol, item.reason) for item in report.withheld] == [
        ("BTC", "provider_symbol_observe_only")
    ]


def test_observe_only_provider_direction_is_journaled_but_not_executed(
    tmp_path: Path,
) -> None:
    """Direction scope blocks auto routing while preserving the research event."""
    runner, engines, telemetry = _runner(
        tmp_path,
        (_intent("ETH", "short"), _intent("SOL", "long")),
        executable_provider_directions=frozenset(
            {
                ("hulk", "ETH", "long"),
                ("hulk", "SOL", "long"),
            }
        ),
    )

    assert runner.run(max_polls=1) == 1

    assert engines["ETH"].entries == []
    assert engines["SOL"].entries[0][0] == "long"
    report = telemetry.routings[0][1]
    assert [(item.intent.symbol, item.reason) for item in report.withheld] == [
        ("ETH", "provider_direction_observe_only")
    ]


class _ReadFailureAfterSubmission(_Engine):
    """An engine whose post-submission verification read fails transiently.

    This is the real shape from `place_and_verify_entry_protection`: the entry and
    the protective stop are already submitted, and the read that confirms the stop
    is visible raises. The position exists; the lifecycle is mid-flight.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(symbol)
        self.submitted = False

    def enter(self, **kwargs: object) -> SolLiveSnapshot:
        self.submitted = True
        self.current = SolLiveSnapshot(state=SolLiveState.PROTECTING)
        raise ServerError(502, "Bad Gateway")


def test_transient_read_failure_before_execution_still_degrades(
    tmp_path: Path,
) -> None:
    """A read-phase transport failure stays a degraded poll, not a crash."""
    runner, engines, telemetry = _runner(tmp_path, ())
    failures = iter([ServerError(502, "Bad Gateway"), None])

    original = engines["BTC"].reconcile_telemetry

    def flaky(**kwargs: object) -> SolReconciliationSnapshot:
        failure = next(failures, None)
        if failure is not None:
            raise failure
        return original(**kwargs)

    engines["BTC"].reconcile_telemetry = flaky

    assert runner.run(max_polls=1) == 1
    assert ("hyperliquid_account_reconciliation", "http_server_retry_exhausted") in (
        telemetry.degraded_polls
    )


def test_read_failure_after_order_submission_is_never_degraded(
    tmp_path: Path,
) -> None:
    """A transport failure raised at or after a mutation must reach the operator.

    Swallowing it leaves the engine mid-lifecycle: `_reconcile_owned_lifecycle`
    branches only on OPEN and FLAT, and the profit-lock, recipe and maximum-hold
    controllers all skip a snapshot that is not OPEN, so a real position would
    never be evaluated for exit again while heartbeats kept reporting `running`.
    """
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    engines["BTC"] = _ReadFailureAfterSubmission("BTC")
    telemetry = _Telemetry(None)
    executable_pairs = frozenset(("hulk", symbol) for symbol in _SYMBOLS)
    runner = MultiAssetLiveRunner(
        symbols=_SYMBOLS,
        engines=engines,
        router=_router(),
        intent_poller=_Poller((_intent("BTC", "long"),), (), ()),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: datetime(2026, 8, 1, 12, tzinfo=UTC),
        sleep_fn=lambda _: None,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in _SYMBOLS},
        execution_contracts={"hulk": _contract()},
        maximum_entry_delay_ms_by_provider_symbol={
            pair: 60_000 for pair in executable_pairs
        },
        executable_provider_symbols=executable_pairs,
    )

    with pytest.raises(ServerError) as raised:
        runner.run(max_polls=1)

    assert engines["BTC"].submitted is True
    assert not telemetry.degraded_polls, (
        "a post-submission failure must not be recorded as a degraded poll"
    )
    # The original fault propagates, so the operator still gets an exact stage
    # instead of a wrapper's "unclassified".
    assert runtime_failure_stage(raised.value) == "entry_submission"
