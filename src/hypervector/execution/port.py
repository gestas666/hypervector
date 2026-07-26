"""Execution-port protocol shared by shadow simulation and live adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hypervector.execution.models import AccountSnapshot, OrderCommand, VenueOrderEvent


@runtime_checkable
class ExecutionPort(Protocol):
    """Backend-facing execution boundary with normalized return types."""

    def submit(self, command: OrderCommand) -> VenueOrderEvent:
        """Submit one command and return its first normalized venue event."""
        ...

    def cancel(
        self,
        client_order_id: str,
        *,
        requested_at: str,
    ) -> VenueOrderEvent:
        """Request cancellation and return its first normalized venue event."""
        ...

    def reconcile(self) -> tuple[VenueOrderEvent, ...]:
        """Return normalized events discovered during venue reconciliation."""
        ...

    def account_snapshot(self) -> AccountSnapshot:
        """Return the latest normalized venue account state."""
        ...
