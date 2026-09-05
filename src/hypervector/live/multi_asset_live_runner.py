from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
import time

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    IntentRoutingReport,
    RoutingAction,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live import cohort_execution_contract_selection as contract_selection
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_entry_submission import (
    EntryDelayMap,
    execute_fresh_routed_actions,
    validate_entry_delays,
)
from hypervector.live.cohort_funding_window import committed_funding_window
from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.cohort_route_cycle import (
    route_cycle,
    validate_and_build_exit_controllers,
)
from hypervector.live.cohort_routing_execution import execute_routing_action
from hypervector.live.cohort_maximum_hold_policy import (
    EvaluationKey,
    update_latest_evaluations,
)
from hypervector.live.multi_asset_execution_authority import (
    create_operator_processor,
    effective_execution_directions,
    hold_milliseconds,
)
from hypervector.live.multi_asset_cohort_telemetry import AssetCohortSnapshot
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    all_flat_and_unowned,
    asset_snapshot,
    aware,
    reconcile_engines,
    remaining_delay,
    shared_account_facts,
    validate_max_polls,
)
from hypervector.live.multi_asset_intent_poller import (
    CohortIntentPoll,
)
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.multi_asset_live_protocols import (
    CohortTelemetryProtocol,
    MultiAssetEngineProtocol,
    MultiAssetIntentPollerProtocol,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.multi_asset_operator_runtime import (
    CohortOperatorExecutionError,
    OperatorCommandSourceProtocol,
)
from hypervector.live.sol_range_onset_state import SolLiveState
from hypervector.live.transient_transport import transient_read_failure_reason

_FUNDING_LOOKBACK_MS = 86_400_000
_ContractMap = Mapping[
    contract_selection.ExecutionContractKey, ProviderExecutionContract
]
_SizingMap = Mapping[tuple[str, str], CohortEntrySizing]
_DirectionalSizingMap = Mapping[tuple[str, str, str], CohortEntrySizing]


class MultiAssetLiveRunner:
    """Reconcile, route, and execute all symbols under one account owner."""

    _funding_start_ms: int | None
    _latest_evaluations: dict[EvaluationKey, ProviderEvaluation]
    _started: bool

    def __init__(
        self,
        *,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        router: BidirectionalIntentRouter,
        intent_poller: MultiAssetIntentPollerProtocol,
        telemetry: CohortTelemetryProtocol,
        stop_file: Path,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        signal_stop_requested: Callable[[], bool],
        maximum_hold_seconds_by_symbol: Mapping[str, int],
        execution_contracts: _ContractMap,
        maximum_entry_delay_ms_by_provider_symbol: EntryDelayMap,
        executable_provider_symbols: frozenset[tuple[str, str]],
        executable_provider_directions: frozenset[tuple[str, str, str]] | None = None,
        provider_entry_sizing: _SizingMap | None = None,
        provider_directional_entry_sizing: _DirectionalSizingMap | None = None,
        operator_commands: OperatorCommandSourceProtocol | None = None,
        transition_drain: CohortTransitionDrain | None = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._assign_strategy_dependencies(
            symbols,
            engines,
            router,
            intent_poller,
            telemetry,
            maximum_hold_seconds_by_symbol,
            execution_contracts,
            maximum_entry_delay_ms_by_provider_symbol,
            executable_provider_symbols,
            executable_provider_directions,
            provider_entry_sizing or {},
            provider_directional_entry_sizing or {},
            operator_commands,
            transition_drain,
            poll_seconds,
        )
        self._assign_runtime_dependencies(
            telemetry,
            stop_file,
            now_fn,
            sleep_fn,
            poll_seconds,
            signal_stop_requested,
            monotonic_fn,
        )

    def _assign_strategy_dependencies(
        self,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        router: BidirectionalIntentRouter,
        intent_poller: MultiAssetIntentPollerProtocol,
        telemetry: CohortTelemetryProtocol,
        maximum_holds: Mapping[str, int],
        contracts: _ContractMap,
        entry_delays: EntryDelayMap,
        executable_pairs: frozenset[tuple[str, str]],
        executable_directions: frozenset[tuple[str, str, str]] | None,
        sizing: _SizingMap,
        directional_sizing: _DirectionalSizingMap,
        operator_commands: OperatorCommandSourceProtocol | None,
        transition_drain: CohortTransitionDrain | None,
        poll_seconds: float,
    ) -> None:
        self._symbols, self._engines = symbols, engines
        self._router, self._intent_poller = router, intent_poller
        self._maximum_hold_ms = hold_milliseconds(maximum_holds)
        effective_directions = self._assign_exit_controllers(
            symbols=symbols,
            engines=engines,
            router=router,
            telemetry=telemetry,
            poll_seconds=poll_seconds,
            contracts=contracts,
            executable_pairs=executable_pairs,
            executable_directions=executable_directions,
            sizing=sizing,
            directional_sizing=directional_sizing,
        )
        self._assign_execution_authority(
            contracts=contracts,
            entry_delays=entry_delays,
            executable_pairs=executable_pairs,
            effective_directions=effective_directions,
            sizing=sizing,
            directional_sizing=directional_sizing,
        )
        self._assign_operator_dependencies(
            operator_commands,
            telemetry,
            engines,
            executable_pairs,
            effective_directions,
            router.maximum_positions,
            transition_drain,
        )

    def _assign_operator_dependencies(
        self,
        commands: OperatorCommandSourceProtocol | None,
        telemetry: CohortTelemetryProtocol,
        engines: Mapping[str, MultiAssetEngineProtocol],
        executable_pairs: frozenset[tuple[str, str]],
        effective_directions: frozenset[tuple[str, str, str]],
        maximum_positions: int,
        transition_drain: CohortTransitionDrain | None,
    ) -> None:
        self._latest_evaluations = {}
        self._operator_processor = create_operator_processor(
            commands,
            telemetry,
            engines,
            executable_pairs,
            effective_directions,
            maximum_positions,
            transition_drain,
        )
        self._transition_drain = transition_drain
        self._transition_drain_complete = False

    def _assign_exit_controllers(
        self,
        *,
        symbols: tuple[str, ...],
        engines: Mapping[str, MultiAssetEngineProtocol],
        router: BidirectionalIntentRouter,
        telemetry: CohortTelemetryProtocol,
        poll_seconds: float,
        contracts: _ContractMap,
        executable_pairs: frozenset[tuple[str, str]],
        executable_directions: frozenset[tuple[str, str, str]] | None,
        sizing: _SizingMap,
        directional_sizing: _DirectionalSizingMap,
    ) -> frozenset[tuple[str, str, str]]:
        effective_directions = effective_execution_directions(
            executable_pairs, executable_directions
        )
        (
            self._maximum_hold_controller,
            self._provider_exit_controller,
            self._profit_lock_controller,
        ) = validate_and_build_exit_controllers(
            symbols=symbols,
            engines=engines,
            router=router,
            poll_seconds=poll_seconds,
            fallback_hold_ms=self._maximum_hold_ms,
            contracts=contracts,
            executable_pairs=executable_pairs,
            executable_directions=effective_directions,
            sizing=sizing,
            directional_sizing=directional_sizing,
            telemetry=telemetry,
        )
        return effective_directions

    def _assign_execution_authority(
        self,
        *,
        contracts: _ContractMap,
        entry_delays: EntryDelayMap,
        executable_pairs: frozenset[tuple[str, str]],
        effective_directions: frozenset[tuple[str, str, str]],
        sizing: _SizingMap,
        directional_sizing: _DirectionalSizingMap,
    ) -> None:
        self._executable_provider_symbols = executable_pairs
        self._executable_provider_directions = effective_directions
        self._execution_contracts = dict(contracts)
        self._maximum_entry_delay_ms = validate_entry_delays(
            entry_delays, executable_pairs
        )
        self._provider_entry_sizing = dict(sizing)
        self._provider_directional_entry_sizing = dict(directional_sizing)

    def _assign_runtime_dependencies(
        self,
        telemetry: CohortTelemetryProtocol,
        stop_file: Path,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        signal_stop_requested: Callable[[], bool],
        monotonic_fn: Callable[[], float],
    ) -> None:
        self._telemetry = telemetry
        self._stop_file = stop_file
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._signal_stop_requested = signal_stop_requested
        self._monotonic_fn = monotonic_fn
        self._funding_start_ms, self._started = None, False

    def start(
        self,
        *,
        activation_time_ms: int,
        start_engines: bool = True,
    ) -> None:
        """Start every symbol once and establish the no-retro-entry boundary."""
        if self._started:
            raise MultiAssetLiveRunnerError("cohort runner has already started")
        if self._shutdown_requested():
            raise MultiAssetLiveRunnerError("operator stop requested before startup")
        if start_engines:
            for symbol in self._symbols:
                self._engines[symbol].start()
        self._intent_poller.activate(activation_time_ms)
        self._funding_start_ms = max(0, activation_time_ms - _FUNDING_LOOKBACK_MS)
        self._telemetry.emit_configuration()
        self._started = True

    def poll_once(self) -> int:
        """Run one deterministic reconcile, intent, execution, and telemetry cycle."""
        if not self._started or self._funding_start_ms is None:
            raise MultiAssetLiveRunnerError("cohort runner is not started")
        funding_start_ms = self._funding_start_ms
        funding_observed = aware(self._now_fn())
        funding_end_ms = int(funding_observed.timestamp() * 1_000)
        venues = reconcile_engines(
            self._symbols, self._engines, funding_start_ms, funding_end_ms
        )
        observed = aware(self._now_fn())
        observed_ms = int(observed.timestamp() * 1_000)
        poll = self._intent_poller.poll(observed)
        self._latest_evaluations = update_latest_evaluations(
            self._latest_evaluations,
            poll.all_evaluations,
        )
        self._telemetry.emit_market_bars(poll.market_bars)
        if poll.regime_evaluations:
            self._telemetry.emit_canonical_regimes(poll.regime_evaluations)
        operator_actions, affected = self._run_operator_commands(poll, observed_ms)
        routed = route_cycle(
            symbols=self._symbols,
            engines=self._engines,
            router=self._router,
            poll=poll,
            observed_ms=observed_ms,
            operator_symbols=affected,
            venues=venues,
            evaluations=self._latest_evaluations,
            maximum_hold=self._maximum_hold_controller,
            recipe_exit=self._provider_exit_controller,
            profit_lock=self._profit_lock_controller,
            executable_pairs=self._executable_provider_symbols,
            executable_directions=self._executable_provider_directions,
            transition_drain=self._transition_drain,
        )
        report = self._finish_cycle(
            poll=poll,
            operator_actions=operator_actions,
            routed=routed,
            routed_actions=routed.actions,
            venues=venues,
            funding_start_ms=funding_start_ms,
            funding_end_ms=funding_end_ms,
            observed_ms=observed_ms,
        )
        return len(report.actions)

    def _finish_cycle(
        self,
        *,
        poll: CohortIntentPoll,
        operator_actions: tuple[RoutingAction, ...],
        routed: IntentRoutingReport,
        routed_actions: tuple[RoutingAction, ...],
        venues: Mapping[str, SolReconciliationSnapshot],
        funding_start_ms: int,
        funding_end_ms: int,
        observed_ms: int,
    ) -> IntentRoutingReport:
        executed, submission_withheld = execute_fresh_routed_actions(
            routed_actions,
            now_ms=lambda: int(aware(self._now_fn()).timestamp() * 1_000),
            delays=self._maximum_entry_delay_ms,
            execute=self._execute,
        )
        report = IntentRoutingReport(
            operator_actions + executed,
            routed.withheld + submission_withheld,
        )
        self._telemetry.emit_routing(
            poll.all_intents, report, poll.telemetry_evaluations
        )
        post_action = bool(report.actions)
        if post_action:
            venues = reconcile_engines(
                self._symbols, self._engines, funding_start_ms, observed_ms
            )
        funding_window = committed_funding_window(
            funding_start_ms, funding_end_ms, observed_ms, len(report.actions)
        )
        self._funding_start_ms = funding_window.next_funding_start_time_ms
        self._telemetry.emit_funding_reconciliation_window(funding_window)
        self._complete_transition_drain_if_ready()
        self._telemetry.emit_snapshot(
            account=shared_account_facts(self._symbols, venues),
            assets=self._asset_snapshots(venues, poll.reference_prices),
        )
        if not self._profit_lock_controller.cycle_degraded:
            self._telemetry.emit_heartbeat()
        return report

    def _run_operator_commands(
        self,
        poll: CohortIntentPoll,
        observed_ms: int,
    ) -> tuple[tuple[RoutingAction, ...], set[str]]:
        if self._operator_processor is None:
            return (), set()
        try:
            return self._operator_processor.process(
                reference_prices=poll.reference_prices,
                observed_ms=observed_ms,
                execute=self._execute,
            )
        except CohortOperatorExecutionError as exc:
            raise MultiAssetLiveRunnerError(str(exc)) from exc

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until explicit stop or a bounded test completion."""
        validate_max_polls(max_polls)
        activation = aware(self._now_fn())
        self.start(activation_time_ms=int(activation.timestamp() * 1_000))
        polls = 0
        while not self._shutdown_requested():
            cycle_started = self._monotonic_fn()
            try:
                self.poll_once()
            except TransientCohortMarketDataError as exc:
                self._telemetry.emit_poll_degraded(
                    source=exc.source,
                    reason=exc.reason,
                )
            except (RequestException, ClientError, ServerError) as exc:
                reason = transient_read_failure_reason(exc)
                if reason is None:
                    raise
                self._telemetry.emit_poll_degraded(
                    source="hyperliquid_account_reconciliation",
                    reason=reason,
                )
            polls += 1
            if self._transition_drain_complete:
                self._stop_all("operator_transition_drain_complete")
                return polls
            if max_polls is not None and polls >= max_polls:
                self._stop_all("bounded_run_complete")
                return polls
            if not self._shutdown_requested():
                elapsed = self._monotonic_fn() - cycle_started
                self._sleep_fn(remaining_delay(self._poll_seconds, elapsed))
        self._stop_all("operator_stop")
        return polls

    def _execute(self, action: RoutingAction) -> None:
        execute_routing_action(
            action,
            engine=self._engines[action.symbol],
            contracts=self._execution_contracts,
            directional_sizing=self._provider_directional_entry_sizing,
            fallback_sizing=self._provider_entry_sizing,
        )

    def _asset_snapshots(
        self,
        venues: tuple[SolReconciliationSnapshot, ...],
        reference_prices: Mapping[str, float],
    ) -> tuple[AssetCohortSnapshot, ...]:
        return tuple(
            asset_snapshot(
                symbol,
                self._engines[symbol].snapshot,
                venue,
                reference_prices.get(symbol),
            )
            for symbol, venue in zip(self._symbols, venues, strict=True)
        )

    def _shutdown_requested(self) -> bool:
        return self._stop_file.exists() or self._signal_stop_requested()

    def _complete_transition_drain_if_ready(self) -> None:
        drain = self._transition_drain
        snapshots = tuple(engine.snapshot for engine in self._engines.values())
        if drain is None or not drain.active or not all_flat_and_unowned(snapshots):
            return
        completed = drain.complete()
        self._transition_drain_complete = True
        self._telemetry.emit_operator_command(
            {
                "request_id": completed.request_id,
                "status": "drained",
                "reason": "portfolio flat with no owned order identities",
                "action": "transition_drain",
                "symbol": "MULTI",
                "provider": None,
                "side": None,
            }
        )

    def _stop_all(self, reason: str) -> None:
        for symbol in self._symbols:
            snapshot = self._engines[symbol].snapshot
            if snapshot.state in {SolLiveState.FLAT, SolLiveState.OPEN}:
                self._engines[symbol].stop(reason)
