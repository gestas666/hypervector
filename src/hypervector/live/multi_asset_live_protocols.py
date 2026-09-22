"""Structural interfaces consumed by the shared live cohort scheduler."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from hypervector.live.bidirectional_intents import IntentRoutingReport, StrategyIntent
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_startup_candle_recorder import StartupCandleObserver
from hypervector.live.cohort_funding_window import CohortFundingWindow
from hypervector.live.entry_submission_deadline import EntrySubmissionDeadline
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot, SolBookSnapshot
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.multi_asset_cohort_telemetry import (
    AssetCohortSnapshot,
    SharedAccountFacts,
)
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll, CohortMarketBar
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.sol_range_onset_state import SolLiveSnapshot


class MultiAssetEngineProtocol(Protocol):
    """Protected symbol lifecycle consumed by the cohort scheduler."""

    @property
    def snapshot(self) -> SolLiveSnapshot: ...

    @property
    def latest_book(self) -> SolBookSnapshot | None: ...

    def start(self) -> SolLiveSnapshot: ...

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot: ...

    def record_strategy_decision(self, payload: dict[str, object]) -> None: ...

    def enter(
        self,
        *,
        side: str,
        mark_price: float,
        decision_time_ms: int | None = None,
        entry_sizing: CohortEntrySizing | None = None,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> SolLiveSnapshot: ...

    def exit(self, *, mark_price: float, reason: str) -> SolLiveSnapshot: ...

    def stop(self, reason: str) -> SolLiveSnapshot: ...


class MultiAssetIntentPollerProtocol(Protocol):
    """Causal multi-provider intent source."""

    def activate(self, activation_time_ms: int) -> None: ...

    def poll(self, observed_at: datetime) -> CohortIntentPoll: ...

    def bind_startup_input_observer(self, observer: StartupCandleObserver) -> None: ...


class CohortTelemetryProtocol(Protocol):
    """Read-only TUI projection boundary."""

    @property
    def adaptive_exit_journal(self) -> AdaptiveExitJournal: ...

    def emit_configuration(self) -> None: ...

    def emit_market_bars(
        self,
        bars: Mapping[str, tuple[CohortMarketBar, ...]],
    ) -> None: ...

    def emit_routing(
        self,
        intents: tuple[StrategyIntent, ...],
        report: IntentRoutingReport,
        evaluations: tuple[ProviderEvaluation, ...] = (),
    ) -> None: ...

    def emit_canonical_regimes(
        self,
        evaluations: tuple[ProviderEvaluation, ...],
    ) -> None: ...

    def emit_snapshot(
        self,
        *,
        account: SharedAccountFacts,
        assets: tuple[AssetCohortSnapshot, ...],
    ) -> None: ...

    def emit_heartbeat(self) -> None: ...

    def emit_funding_reconciliation_window(
        self, window: CohortFundingWindow
    ) -> None: ...

    def emit_poll_degraded(self, *, source: str, reason: str) -> None: ...

    def emit_operator_command(self, payload: Mapping[str, object]) -> None: ...

    def recorded_maximum_hold_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None: ...

    def emit_maximum_hold_decision(self, payload: Mapping[str, object]) -> None: ...

    def recorded_provider_exit_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None: ...

    def emit_provider_exit_decision(self, payload: Mapping[str, object]) -> None: ...

    def recorded_profit_lock_decision(
        self, decision_id: str
    ) -> Mapping[str, object] | None: ...

    def emit_profit_lock_decision(self, payload: Mapping[str, object]) -> None: ...
