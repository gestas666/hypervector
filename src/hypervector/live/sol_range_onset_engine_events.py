"""Execution-event facade shared by the SOL live lifecycle."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry
from hypervector.live.sol_range_onset_state import SolLiveStateMachine


class SolLiveEngineEvents:
    """Keep state transitions and authoritative telemetry writes synchronized."""

    def __init__(
        self,
        *,
        telemetry: SolLiveTelemetry,
        machine: SolLiveStateMachine,
    ) -> None:
        self._telemetry = telemetry
        self._machine = machine

    def emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Write one authoritative live event."""
        self._telemetry.emit(event_type, payload)

    def emit_state(self) -> None:
        """Write the complete current recoverable state."""
        self._telemetry.emit_state(self._machine.snapshot)

    def emit_preflight(
        self,
        preflight: SolVenuePreflight,
        venue: SolReconciliationSnapshot,
    ) -> None:
        """Write venue/configuration preflight facts."""
        self._telemetry.emit_preflight(preflight, venue)

    def emit_reconciliation(self, venue: SolReconciliationSnapshot) -> None:
        """Write one authoritative venue reconciliation."""
        self._telemetry.emit_reconciliation(venue)

    def emit_ack(
        self,
        operation: str,
        ack: HyperliquidOrderAck,
        *,
        event_type: str = "order_acknowledgement",
    ) -> None:
        """Write one normalized exchange acknowledgement."""
        self._telemetry.emit_ack(operation, ack, event_type=event_type)

    def emit_close_intent(self, *, reason: str, stop_oid: int) -> None:
        """Persist why an exit began before mutating venue orders."""
        self.emit("close", {"reason": reason, "intent": True, "stop_oid": stop_oid})

    def emit_close_complete(self, *, reason: str, oid: int) -> None:
        """Persist a strategy close after venue-flat reconciliation."""
        self.emit("close", {"reason": reason, "oid": oid, "verified_flat": True})

    def confirm_entry_not_filled(self, *, reason: str) -> None:
        """Persist a definitive IOC no-fill and the resulting flat state."""
        self._machine.confirm_entry_not_filled()
        self.emit("entry_not_filled", {"reason": reason, "verified_flat": True})
        self.emit_state()

    def fault(self, reason: str) -> None:
        """Enter fault state and persist the reason plus resulting state."""
        self._machine.fault(reason)
        self.emit("fault", {"reason": reason})
        self.emit_state()

    def confirm_protective_stop_fill(self, *, stop_oid: int) -> None:
        """Persist an exact owned native-stop completion and resulting FLAT state."""
        self._machine.confirm_protective_stop_fill(stop_oid=stop_oid)
        self.emit(
            "close",
            {"reason": "protective_stop", "oid": stop_oid, "verified_flat": True},
        )
        self.emit_state()

    def confirm_owned_bracket_exit(
        self,
        *,
        reason: str,
        owned_oids: tuple[int, ...],
    ) -> None:
        """Persist an exact stop, target, or mixed bracket completion."""
        self._machine.confirm_owned_bracket_exit()
        self.emit(
            "close",
            {
                "reason": reason,
                "owned_oids": list(owned_oids),
                "verified_flat": True,
            },
        )
        self.emit_state()

    def confirm_stop_fill_during_protection(self, *, stop_oid: int) -> None:
        """Persist a native stop that filled before the lifecycle reached OPEN."""
        self._machine.confirm_protective_stop_fill_during_protection(stop_oid=stop_oid)
        self.emit(
            "close",
            {
                "reason": "protective_stop_during_protection",
                "oid": stop_oid,
                "verified_flat": True,
            },
        )
        self.emit_state()

    def confirm_target_fill_during_protection(self, *, target_oid: int) -> None:
        """Persist a target that filled while the bracket was being placed."""
        self._machine.confirm_target_fill_during_protection(target_oid=target_oid)
        self.emit(
            "close",
            {
                "reason": "target_during_protection",
                "oid": target_oid,
                "verified_flat": True,
            },
        )
        self.emit_state()

    def confirm_stop_fill_during_exit(
        self,
        *,
        stop_oid: int,
        reason: str = "replacement_protective_stop_during_exit",
    ) -> None:
        """Persist a replacement stop that flattened residual exit exposure."""
        self._machine.confirm_protective_stop_fill_during_exit(stop_oid=stop_oid)
        self.emit(
            "close",
            {
                "reason": reason,
                "oid": stop_oid,
                "verified_flat": True,
            },
        )
        self.emit_state()

    def emit_recovered_stop_fill(self, *, stop_oid: int) -> None:
        """Persist an owned stop completion discovered during restart preflight."""
        self.emit(
            "close",
            {
                "reason": "protective_stop_restart_recovery",
                "oid": stop_oid,
                "verified_flat": True,
            },
        )
