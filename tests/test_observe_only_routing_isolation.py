"""Regression tests for strict separation of observation and execution authority."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from multi_asset_live_runner_fixtures import execution_contract, venue_snapshot

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_funding_window import CohortFundingWindow
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_OBSERVED_AT = datetime(2026, 8, 5, 12, tzinfo=UTC)
_OBSERVED_MS = int(_OBSERVED_AT.timestamp() * 1_000)


class _Engine:
    """Record executions while exposing one deterministic venue lifecycle."""

    def __init__(self, snapshot: SolLiveSnapshot | None = None) -> None:
        self.current = snapshot or SolLiveSnapshot(state=SolLiveState.FLAT)
        self.entries: list[str] = []
        self.exits: list[str] = []

    @property
    def snapshot(self) -> SolLiveSnapshot:
        """Return the current deterministic lifecycle."""
        return self.current

    def start(self) -> SolLiveSnapshot:
        """Start flat for the entry-isolation scenario."""
        self.current = SolLiveSnapshot(state=SolLiveState.FLAT)
        return self.current

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        """Return venue facts matching the current signed position."""
        del funding_start_time_ms, funding_end_time_ms
        return venue_snapshot(self.current.position_size_signed)

    def record_strategy_decision(self, payload: dict[str, object]) -> None:
        """Accept decision telemetry without changing the test lifecycle."""
        del payload

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
        entry_sizing: CohortEntrySizing | None = None,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> SolLiveSnapshot:
        """Record the selected entry and project an open position."""
        del mark_price, entry_sizing
        if decision_time_ms is None:
            raise ValueError("test entry requires a decision timestamp")
        if entry_deadline is not None:
            entry_deadline.check("adapter_dispatch")
        self.entries.append(side)
        signed = 1.0 if side == "long" else -1.0
        self.current = SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=1,
            stop_oid=2,
            position_size_signed=signed,
            opened_at_ms=decision_time_ms,
        )
        return self.current

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot:
        """Record an exit so an unauthorized close is observable."""
        del mark_price
        self.exits.append(reason)
        self.current = SolLiveSnapshot(state=SolLiveState.FLAT)
        return self.current

    def stop(self, reason: str) -> SolLiveSnapshot:
        """Project a stopped lifecycle at bounded-test completion."""
        self.current = replace(
            self.current,
            state=SolLiveState.STOPPED,
            stop_reason=reason,
        )
        return self.current


class _Poller:
    """Return one fixed same-symbol executable/observe-only conflict."""

    def __init__(self, intents: tuple[StrategyIntent, ...]) -> None:
        self._intents = intents

    def activate(self, activation_time_ms: int) -> None:
        """Accept the causal activation boundary."""
        if activation_time_ms != _OBSERVED_MS:
            raise ValueError("unexpected activation boundary")

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Return the fixed intents at one completed reference price."""
        if observed_at != _OBSERVED_AT:
            raise ValueError("unexpected observation clock")
        return CohortIntentPoll(self._intents, {"BTC": 100.0})


class _Telemetry:
    """Capture routing reports while satisfying the live telemetry protocol."""

    def __init__(self) -> None:
        self.reports: list[object] = []

    def emit_configuration(self) -> None:
        """Accept configuration telemetry."""

    def emit_market_bars(self, bars: object) -> None:
        """Accept market-bar telemetry."""
        del bars

    def emit_routing(
        self,
        intents: object,
        report: object,
        evaluations: object,
    ) -> None:
        """Capture the exact routing report for assertions."""
        del intents, evaluations
        self.reports.append(report)

    def emit_snapshot(self, *, account: object, assets: object) -> None:
        """Accept account and asset telemetry."""
        del account, assets

    def emit_heartbeat(self) -> None:
        """Accept the cycle heartbeat."""

    def emit_funding_reconciliation_window(self, window: CohortFundingWindow) -> None:
        """Accept typed funding-cursor evidence without execution effects."""
        if window.next_funding_start_time_ms != window.committed_funding_end_time_ms:
            raise AssertionError("funding cursor is not contiguous")

    def recorded_maximum_hold_decision(
        self, decision_id: str
    ) -> dict[str, object] | None:
        """Report no prior timer decision in this bounded scenario."""
        del decision_id
        return None

    def emit_maximum_hold_decision(self, payload: dict[str, object]) -> None:
        """Reject an unexpected timer boundary during the test cycle."""
        raise AssertionError(f"unexpected maximum-hold decision: {payload}")


def _intent(strategy: str, side: str) -> StrategyIntent:
    return StrategyIntent(strategy, "BTC", side, _OBSERVED_MS, 100.0, "test")


def _runner(
    tmp_path: Path,
    engine: _Engine,
    intents: tuple[StrategyIntent, ...],
) -> tuple[MultiAssetLiveRunner, _Telemetry]:
    capabilities = tuple(
        StrategyCapability(strategy, "BTC", frozenset({"long", "short"}), priority)
        for strategy, priority in (("hulk", 10), ("hype", 100))
    )
    telemetry = _Telemetry()
    runner = MultiAssetLiveRunner(
        symbols=("BTC",),
        engines={"BTC": engine},
        router=BidirectionalIntentRouter(capabilities, maximum_positions=1),
        intent_poller=_Poller(intents),
        telemetry=telemetry,
        stop_file=tmp_path / "STOP",
        now_fn=lambda: _OBSERVED_AT,
        sleep_fn=lambda _: None,
        poll_seconds=60.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={"BTC": 28_800},
        execution_contracts={"hulk": execution_contract()},
        maximum_entry_delay_ms_by_provider_symbol={("hulk", "BTC"): 60_000},
        executable_provider_symbols=frozenset({("hulk", "BTC")}),
    )
    return runner, telemetry


def test_observe_only_conflict_cannot_suppress_executable_entry(tmp_path: Path) -> None:
    """A higher-priority observe-only opposite signal cannot win arbitration."""
    engine = _Engine()
    runner, telemetry = _runner(
        tmp_path,
        engine,
        (_intent("hype", "short"), _intent("hulk", "long")),
    )

    assert runner.run(max_polls=1) == 1

    assert engine.entries == ["long"]
    assert engine.exits == []
    report = telemetry.reports[0]
    assert report.actions[0].strategy_id == "hulk"
    assert [(item.intent.strategy_id, item.reason) for item in report.withheld] == [
        ("hype", "provider_symbol_observe_only")
    ]


def test_observe_only_opposite_signal_cannot_close_open_position(
    tmp_path: Path,
) -> None:
    """An observe-only opposite intent cannot close an executable lifecycle."""
    engine = _Engine(
        SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=1,
            stop_oid=2,
            position_size_signed=1.0,
            opened_at_ms=_OBSERVED_MS - 1_000,
        )
    )
    runner, telemetry = _runner(tmp_path, engine, (_intent("hype", "short"),))
    runner.start(activation_time_ms=_OBSERVED_MS, start_engines=False)

    assert runner.poll_once() == 0

    assert engine.entries == []
    assert engine.exits == []
    report = telemetry.reports[0]
    assert report.actions == ()
    assert [(item.intent.strategy_id, item.reason) for item in report.withheld] == [
        ("hype", "provider_symbol_observe_only")
    ]
