"""Network-free clock and venue fixtures for entry dispatch deadlines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from multi_asset_live_runner_fixtures import execution_contract
from test_multi_asset_live_runner import _Telemetry
from test_asset_live_engine import FakeVenueAdapter, _order, _runtime, _venue

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidReconciliationSnapshot,
)
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_ledger import AssetLiveLedger

if TYPE_CHECKING:
    from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline

EPOCH = datetime(2026, 9, 8, 6, tzinfo=UTC)
DECISION_MS = int(EPOCH.timestamp() * 1_000)
ROUTE = ("offline_timing_probe", "SOL")


@dataclass(frozen=True)
class Case:
    """Independent injected stage delays, expressed in exact microseconds."""

    name: str
    initial_age_us: int
    provider_delay_us: int = 0
    flat_check_delay_us: int = 0
    deadline_ms: int = 30_000
    persistence_delay_us: int = 0


@dataclass
class Clock:
    """A deterministic process clock that never sleeps in real time."""

    offset_us: int = 0

    def now(self) -> datetime:
        """Return the current synthetic timestamp."""
        return EPOCH + timedelta(microseconds=self.offset_us)

    def milliseconds(self) -> int:
        """Return exact integer epoch milliseconds."""
        return DECISION_MS + self.offset_us // 1_000

    def sleep(self, seconds: float) -> None:
        """Advance the test clock instead of waiting."""
        self.offset_us += round(seconds * 1_000_000)


class TimedAdapter(FakeVenueAdapter):
    """Use existing test responses and record the fake dispatch boundary."""

    def __init__(self, clock: Clock, case: Case) -> None:
        super().__init__(reconciliations())
        self.clock, self.case = clock, case
        self.read_count = 0
        self.entry_times_ms: list[int] = []

    def reconcile(self) -> HyperliquidReconciliationSnapshot:
        """Delay only the pre-entry flat verification."""
        self.read_count += 1
        if self.read_count == 3:
            self.clock.offset_us += self.case.flat_check_delay_us
        return super().reconcile()

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        client_order_id: str,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> HyperliquidOrderAck:
        """Model the adapter's final check before its fake SDK dispatch."""
        if entry_deadline is not None:
            entry_deadline.check("sdk_dispatch")
        self.entry_times_ms.append(self.clock.milliseconds())
        return super().submit_entry(
            side=side,
            requested_notional_usd=requested_notional_usd,
            mark_price=mark_price,
            client_order_id=client_order_id,
        )


def reconciliations() -> list[HyperliquidReconciliationSnapshot]:
    """Return startup, cycle, entry and full-size protection responses."""
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    return [
        _venue(0),
        _venue(0),
        _venue(0),
        _venue(0.30),
        _venue(0.30, (stop,)),
        _venue(0.30, (stop,)),
    ]


class TimedPoller:
    """Emit one synthetic intent after a controlled provider delay."""

    def __init__(self, clock: Clock, case: Case) -> None:
        self.clock, self.case = clock, case
        self.decision_ms = DECISION_MS

    def activate(self, activation_time_ms: int) -> None:
        """Require startup at the explicit decision boundary."""
        assert activation_time_ms == DECISION_MS

    def poll(self, observed_at: datetime) -> CohortIntentPoll:
        """Advance provider elapsed time without changing the signal reference."""
        assert observed_at == self.clock.now()
        self.clock.offset_us += self.case.provider_delay_us
        return CohortIntentPoll(
            (StrategyIntent(*ROUTE, "long", self.decision_ms, 73.0, "probe"),),
            {ROUTE[1]: 73.0},
        )


@dataclass
class Scenario:
    """Inspectable real runner/engine with fake external dependencies."""

    runner: MultiAssetLiveRunner
    engine: AssetLiveEngine
    adapter: TimedAdapter
    telemetry: _Telemetry
    clock: Clock
    poller: TimedPoller
    ledger: AssetLiveLedger


def scenario(directory: Path, case: Case) -> Scenario:
    """Build a real entry lifecycle with no signing client or network access."""
    clock = Clock()
    adapter, telemetry = TimedAdapter(clock, case), _Telemetry()
    config, ledger = _runtime(directory)
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    poller = TimedPoller(clock, case)
    router = BidirectionalIntentRouter(
        (StrategyCapability(*ROUTE, frozenset({"long"}), 10),),
        maximum_positions=1,
    )
    runner = MultiAssetLiveRunner(
        symbols=(ROUTE[1],),
        engines={ROUTE[1]: engine},
        router=router,
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=directory / "STOP",
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        poll_seconds=15.0,
        signal_stop_requested=lambda: False,
        maximum_hold_seconds_by_symbol={ROUTE[1]: 86_400},
        execution_contracts={ROUTE[0]: execution_contract()},
        maximum_entry_delay_ms_by_provider_symbol={ROUTE: case.deadline_ms},
        executable_provider_symbols=frozenset({ROUTE}),
    )
    runner.start(activation_time_ms=DECISION_MS)
    clock.offset_us = case.initial_age_us
    return Scenario(runner, engine, adapter, telemetry, clock, poller, ledger)
