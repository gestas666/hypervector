"""Integrated pure coordinator and event-driven shadow execution port."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent, StreamGap
from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.nautilus_shadow import NautilusShadowExecutionPort
from hypervector.paper.shadow_execution_models import ShadowExecutionRecord
from hypervector.strategies.hypervelocity_runtime import (
    HypervelocityRuntimeState,
    RuntimeDecision,
    RuntimeMarketState,
    advance_hypervelocity_runtime,
)


@dataclass(frozen=True)
class ShadowCycle:
    """One controller advance and every execution-side effect it produced."""

    commands: tuple[OrderCommand, ...]
    cancellations: tuple[str, ...]
    venue_events: tuple[VenueOrderEvent, ...]
    execution_records: tuple[ShadowExecutionRecord, ...]
    annotations: tuple[str, ...]


class HypervelocityShadowController:
    """Coordinate strategy decisions and public event evidence without I/O."""

    def __init__(
        self,
        *,
        port: NautilusShadowExecutionPort,
        initial_market: RuntimeMarketState,
        initial_state: HypervelocityRuntimeState | None = None,
        initial_commands: tuple[OrderCommand, ...] = (),
    ) -> None:
        self._port = port
        self._market = initial_market
        self._state = initial_state or HypervelocityRuntimeState()
        self._commands = {
            command.client_order_id: command for command in initial_commands
        }
        self._record_count = len(port.execution_records())

    @property
    def state(self) -> HypervelocityRuntimeState:
        """Return the latest immutable coordinator state."""
        return self._state

    @property
    def port(self) -> NautilusShadowExecutionPort:
        """Return the shadow execution boundary for account telemetry."""
        return self._port

    def command_for(self, client_order_id: str) -> OrderCommand:
        """Return the immutable command associated with a venue event."""
        command = self._commands.get(client_order_id)
        if command is None:
            raise KeyError(client_order_id)
        return command

    def on_market(self, market: RuntimeMarketState) -> ShadowCycle:
        """Apply one pre-classified backend market decision."""
        self._market = replace(
            market,
            evidence_fresh=self._port.evidence_fresh_at(market.observed_at),
        )
        decision = advance_hypervelocity_runtime(self._state, self._market)
        return self._execute(decision, (), ())

    def ingest(
        self,
        event: L2SnapshotEvent | PublicTradeEvent | StreamGap,
    ) -> ShadowCycle:
        """Apply one public venue event and route normalized order transitions."""
        self._port.ingest(event)
        self._market = replace(
            self._market,
            observed_at=_event_timestamp(event),
            evidence_fresh=self._port.evidence_fresh,
        )
        venue_events = self._port.reconcile()
        all_records = self._port.execution_records()
        records = all_records[self._record_count :]
        self._record_count = len(all_records)
        decision = advance_hypervelocity_runtime(
            self._state,
            self._market,
            venue_events,
        )
        return self._execute(decision, venue_events, records)

    def reconcile_liquidation(self, observed_at: str) -> ShadowCycle:
        """Reconcile a port-confirmed isolated liquidation into runtime state."""
        if self._port.last_liquidation is None:
            raise RuntimeError("shadow port has no liquidation to reconcile")
        direction = self._state.position_direction
        if direction is None or self._state.position_quantity <= 0.0:
            raise RuntimeError("runtime has no open position to liquidate")
        liquidation = self._port.last_liquidation
        remaining = liquidation.remaining_quantity
        terminal = list(self._state.terminal_order_ids)
        if self._state.pending_entry is not None:
            terminal.append(self._state.pending_entry.command.client_order_id)
        terminal.extend(
            target.command.client_order_id for target in self._state.active_targets
        )
        state = replace(
            self._state,
            pending_entry=None,
            active_targets=(),
            terminal_order_ids=tuple(dict.fromkeys(terminal)),
            position_direction=direction if remaining > 1e-12 else None,
            position_quantity=remaining,
            position_average_price=(
                self._state.position_average_price if remaining > 1e-12 else None
            ),
            completed_trade_direction=(direction if remaining <= 1e-12 else None),
            last_exit_at=(observed_at if remaining <= 1e-12 else None),
        )
        self._market = replace(self._market, observed_at=observed_at)
        venue_events = self._port.reconcile()
        decision = advance_hypervelocity_runtime(state, self._market)
        return self._execute(
            decision,
            venue_events,
            (),
        )

    def _execute(
        self,
        decision: RuntimeDecision,
        venue_events: tuple[VenueOrderEvent, ...],
        execution_records: tuple[ShadowExecutionRecord, ...],
    ) -> ShadowCycle:
        self._state = decision.state
        immediate: list[VenueOrderEvent] = []
        for client_order_id in decision.cancellations:
            immediate.append(
                self._port.cancel(
                    client_order_id,
                    requested_at=self._market.observed_at,
                )
            )
        for command in decision.commands:
            self._commands[command.client_order_id] = command
            immediate.append(self._port.submit(command))
        return ShadowCycle(
            commands=decision.commands,
            cancellations=decision.cancellations,
            venue_events=venue_events + tuple(immediate),
            execution_records=execution_records,
            annotations=decision.annotations,
        )


def _event_timestamp(
    event: L2SnapshotEvent | PublicTradeEvent | StreamGap,
) -> str:
    if isinstance(event, StreamGap):
        seconds = event.detected_ts_ns / 1_000_000_000
    else:
        seconds = event.exchange_ts_ms / 1_000
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
