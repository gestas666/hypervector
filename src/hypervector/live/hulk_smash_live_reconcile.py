"""Bounded reconciliation polling for the Hulk live lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetry
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot


@dataclass(frozen=True)
class HulkReconciliationResult:
    """Last venue snapshot and whether the requested condition converged."""

    snapshot: SolReconciliationSnapshot
    matched: bool


class HulkSmashReconciler:
    """Own one bounded retry policy for all lifecycle reconciliation."""

    def __init__(
        self,
        *,
        adapter: HulkSmashVenueProtocol,
        telemetry: HulkSmashLiveTelemetry,
        attempts: int,
        delay_seconds: float,
        sleep_fn: Callable[[float], None],
    ) -> None:
        self._adapter = adapter
        self._telemetry = telemetry
        self._attempts = attempts
        self._delay_seconds = delay_seconds
        self._sleep_fn = sleep_fn

    def until(
        self,
        predicate: Callable[[SolReconciliationSnapshot], bool],
    ) -> HulkReconciliationResult:
        """Return the matched or final snapshot under the frozen retry policy."""
        return reconcile_until(
            adapter=self._adapter,
            telemetry=self._telemetry,
            predicate=predicate,
            attempts=self._attempts,
            delay_seconds=self._delay_seconds,
            sleep_fn=self._sleep_fn,
        )


def reconcile_until(
    *,
    adapter: HulkSmashVenueProtocol,
    telemetry: HulkSmashLiveTelemetry,
    predicate: Callable[[SolReconciliationSnapshot], bool],
    attempts: int,
    delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> HulkReconciliationResult:
    """Poll a bounded number of times and retain the final venue truth."""
    latest: SolReconciliationSnapshot | None = None
    for attempt in range(attempts):
        latest = adapter.reconcile()
        telemetry.emit_reconciliation(latest)
        if predicate(latest):
            return HulkReconciliationResult(latest, True)
        if attempt + 1 < attempts:
            sleep_fn(delay_seconds)
    if latest is None:
        raise RuntimeError("reconciliation requires at least one attempt")
    return HulkReconciliationResult(latest, False)
