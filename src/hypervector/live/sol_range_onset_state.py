"""Pure execution-state contract for the SOL range-onset live canary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math

from hypervector.live.cohort_execution_plan import BoundExecutionPlan


class SolLiveState(str, Enum):
    """Mutually exclusive lifecycle states for one SOL execution authority."""

    DISARMED = "DISARMED"
    PREFLIGHT = "PREFLIGHT"
    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    PROTECTING = "PROTECTING"
    TARGET_PENDING = "TARGET_PENDING"
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    FAULTED = "FAULTED"
    STOPPED = "STOPPED"


class SolLiveStateError(RuntimeError):
    """A requested transition violates the SOL canary lifecycle."""


@dataclass(frozen=True)
class SolLiveSnapshot:
    """Auditable state and known venue identities for one SOL position."""

    state: SolLiveState = SolLiveState.DISARMED
    entry_oid: int | None = None
    stop_oid: int | None = None
    target_oid: int | None = None
    close_oid: int | None = None
    position_size_signed: float = 0.0
    opened_at_ms: int | None = None
    last_fault: str | None = None
    stop_reason: str | None = None
    execution_plan: BoundExecutionPlan | None = None
    target_price: float | None = None


class SolLiveStateMachine:
    """Enforce protection, flat-before-entry, and restart invariants."""

    def __init__(self) -> None:
        self._snapshot = SolLiveSnapshot()

    @property
    def snapshot(self) -> SolLiveSnapshot:
        """Return the current immutable lifecycle snapshot."""
        return self._snapshot

    def begin_preflight(self) -> None:
        """Move a disarmed process into read/reconcile-only preflight."""
        self._require(SolLiveState.DISARMED, "begin_preflight")
        self._snapshot = replace(self._snapshot, state=SolLiveState.PREFLIGHT)

    def confirm_preflight_flat(self) -> None:
        """Confirm venue reconciliation found no SOL exposure or orders."""
        self._require(SolLiveState.PREFLIGHT, "confirm_preflight_flat")
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def restore_protected_position(
        self,
        *,
        entry_oid: int,
        stop_oid: int,
        position_size_signed: float,
        opened_at_ms: int,
        execution_plan: BoundExecutionPlan | None = None,
        target_oid: int | None = None,
        target_price: float | None = None,
    ) -> None:
        """Restore only an owned, venue-verified position and protective stop."""
        self._require(SolLiveState.PREFLIGHT, "restore_protected_position")
        size = float(position_size_signed)
        if size == 0.0:
            raise SolLiveStateError("restored position size must be nonzero")
        self._snapshot = _owned_position_snapshot(
            state=SolLiveState.OPEN,
            entry_oid=entry_oid,
            stop_oid=stop_oid,
            target_oid=target_oid,
            position_size_signed=size,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
            target_price=target_price,
        )

    def restore_pending_entry(
        self,
        *,
        entry_oid: int,
        execution_plan: BoundExecutionPlan | None = None,
    ) -> None:
        """Restore a venue-verified committed entry before adding protection."""
        self._require(SolLiveState.PREFLIGHT, "restore_pending_entry")
        self._snapshot = SolLiveSnapshot(
            state=SolLiveState.ENTRY_PENDING,
            entry_oid=_oid(entry_oid, "entry_oid"),
            execution_plan=execution_plan,
        )

    def restore_protecting_position(
        self,
        *,
        entry_oid: int,
        position_size_signed: float,
        opened_at_ms: int,
        execution_plan: BoundExecutionPlan | None = None,
    ) -> None:
        """Restore venue exposure whose committed stop is being recovered."""
        self._require(SolLiveState.PREFLIGHT, "restore_protecting_position")
        self._snapshot = _owned_position_snapshot(
            state=SolLiveState.PROTECTING,
            entry_oid=entry_oid,
            stop_oid=None,
            position_size_signed=position_size_signed,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
        )

    def restore_exit_pending(
        self,
        *,
        entry_oid: int,
        stop_oid: int,
        position_size_signed: float,
        opened_at_ms: int,
        execution_plan: BoundExecutionPlan | None = None,
        target_oid: int | None = None,
        target_price: float | None = None,
    ) -> None:
        """Restore exact ownership while a committed close is resolved."""
        self._require(SolLiveState.PREFLIGHT, "restore_exit_pending")
        self._snapshot = _owned_position_snapshot(
            state=SolLiveState.EXIT_PENDING,
            entry_oid=entry_oid,
            stop_oid=stop_oid,
            position_size_signed=position_size_signed,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
            target_oid=target_oid,
            target_price=target_price,
        )

    def restore_target_pending(
        self,
        *,
        entry_oid: int,
        stop_oid: int,
        position_size_signed: float,
        opened_at_ms: int,
        target_price: float,
        execution_plan: BoundExecutionPlan,
    ) -> None:
        """Restore protected exposure whose target mutation is unresolved."""
        self._require(SolLiveState.PREFLIGHT, "restore_target_pending")
        size = float(position_size_signed)
        if size == 0.0:
            raise SolLiveStateError("restored position size must be nonzero")
        self._snapshot = SolLiveSnapshot(
            state=SolLiveState.TARGET_PENDING,
            entry_oid=_oid(entry_oid, "entry_oid"),
            stop_oid=_oid(stop_oid, "stop_oid"),
            position_size_signed=size,
            opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
            execution_plan=execution_plan,
            target_price=_positive_price(target_price, "target_price"),
        )

    def begin_entry(
        self,
        *,
        execution_plan: BoundExecutionPlan | None = None,
    ) -> None:
        """Reserve the sole SOL entry slot from a verified-flat state."""
        self._require(SolLiveState.FLAT, "begin_entry")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.ENTRY_PENDING,
            execution_plan=execution_plan,
        )

    def acknowledge_entry(self, entry_oid: int) -> None:
        """Attach the venue order ID without claiming an actual fill."""
        self._require(SolLiveState.ENTRY_PENDING, "acknowledge_entry")
        self._snapshot = replace(self._snapshot, entry_oid=_oid(entry_oid, "entry_oid"))

    def begin_protection(
        self,
        *,
        position_size_signed: float,
        opened_at_ms: int,
    ) -> None:
        """Record reconciled exposure before submitting its venue stop."""
        self._require(SolLiveState.ENTRY_PENDING, "begin_protection")
        if self._snapshot.entry_oid is None:
            raise SolLiveStateError(
                "entry acknowledgement is required before protection"
            )
        size = float(position_size_signed)
        if size == 0.0:
            raise SolLiveStateError("protected position size must be nonzero")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.PROTECTING,
            position_size_signed=size,
            opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
        )

    def confirm_protection(self, *, stop_oid: int) -> None:
        """Mark exposure open only after a stop has a venue order ID."""
        self._require(SolLiveState.PROTECTING, "confirm_protection")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.OPEN,
            stop_oid=_oid(stop_oid, "stop_oid"),
        )

    def begin_target(self, *, stop_oid: int, target_price: float) -> None:
        """Persist stop ownership before submitting a required target."""
        self._require(SolLiveState.PROTECTING, "begin_target")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.TARGET_PENDING,
            stop_oid=_oid(stop_oid, "stop_oid"),
            target_price=_positive_price(target_price, "target_price"),
        )

    def confirm_target(self, *, target_oid: int) -> None:
        """Report OPEN only after the complete bracket is venue-visible."""
        self._require(SolLiveState.TARGET_PENDING, "confirm_target")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.OPEN,
            target_oid=_oid(target_oid, "target_oid"),
        )

    def confirm_target_fill_during_protection(self, *, target_oid: int) -> None:
        """Clear exposure when a new target fills before OPEN is emitted."""
        self._require(SolLiveState.TARGET_PENDING, "confirm_target_fill")
        _oid(target_oid, "target_oid")
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def confirm_protective_stop_fill_during_protection(self, *, stop_oid: int) -> None:
        """Clear exposure when the exact new stop fills before becoming OPEN."""
        self._require(SolLiveState.PROTECTING, "confirm_stop_fill")
        _oid(stop_oid, "stop_oid")
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def confirm_protective_stop_fill_during_exit(self, *, stop_oid: int) -> None:
        """Clear residual exposure when its replacement stop fills during exit."""
        self._require(SolLiveState.EXIT_PENDING, "confirm_stop_fill_during_exit")
        _oid(stop_oid, "stop_oid")
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def begin_exit(self) -> None:
        """Reserve the lifecycle for exact stop cancellation and close."""
        self._require(SolLiveState.OPEN, "begin_exit")
        if self._snapshot.stop_oid is None:
            raise SolLiveStateError("open position has no known protective stop")
        self._snapshot = replace(self._snapshot, state=SolLiveState.EXIT_PENDING)

    def confirm_protective_stop_fill(self, *, stop_oid: int) -> None:
        """Clear OPEN only after the venue reports the exact owned stop fill."""
        self._require(SolLiveState.OPEN, "confirm_protective_stop_fill")
        observed = _oid(stop_oid, "stop_oid")
        if self._snapshot.stop_oid != observed:
            raise SolLiveStateError(
                f"protective stop fill oid {observed} does not match owned stop"
            )
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def confirm_owned_bracket_exit(self) -> None:
        """Clear OPEN after an exact owned bracket lifecycle reconciles flat."""
        if self._snapshot.state not in {
            SolLiveState.OPEN,
            SolLiveState.EXIT_PENDING,
        }:
            raise SolLiveStateError(
                f"{self._snapshot.state.value} cannot confirm owned bracket exit"
            )
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def begin_target_after_exit_failure(self, *, target_price: float) -> None:
        """Restore target placement while retaining the original venue stop."""
        self._require(SolLiveState.EXIT_PENDING, "begin_target_after_exit_failure")
        if self._snapshot.stop_oid is None:
            raise SolLiveStateError("target restoration requires an owned stop")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.TARGET_PENDING,
            target_oid=None,
            target_price=_positive_price(target_price, "target_price"),
            close_oid=None,
        )

    def acknowledge_close(self, close_oid: int) -> None:
        """Attach the reduce-only close order ID pending flat reconciliation."""
        self._require(SolLiveState.EXIT_PENDING, "acknowledge_close")
        self._snapshot = replace(self._snapshot, close_oid=_oid(close_oid, "close_oid"))

    def restore_protection_after_exit_failure(self, *, stop_oid: int) -> None:
        """Return to OPEN after a failed close is re-protected at the venue."""
        self._require(
            SolLiveState.EXIT_PENDING, "restore_protection_after_exit_failure"
        )
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.OPEN,
            stop_oid=_oid(stop_oid, "stop_oid"),
            close_oid=None,
        )

    def confirm_flat(self) -> None:
        """Clear order identity only after venue reconciliation verifies flat."""
        self._require(SolLiveState.EXIT_PENDING, "confirm_flat")
        if self._snapshot.close_oid is None:
            raise SolLiveStateError("close acknowledgement is required before flat")
        self._snapshot = SolLiveSnapshot(state=SolLiveState.FLAT)

    def fault(self, reason: str) -> None:
        """Enter an explicit fault while preserving known venue identity."""
        message = reason.strip()
        if not message:
            raise SolLiveStateError("fault reason must be non-empty")
        if self._snapshot.state is SolLiveState.STOPPED:
            raise SolLiveStateError("STOPPED cannot transition via fault")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.FAULTED,
            last_fault=message,
        )

    def stop(self, reason: str) -> None:
        """Stop without removing a known venue-native protective order."""
        message = reason.strip()
        if not message:
            raise SolLiveStateError("stop reason must be non-empty")
        state = self._snapshot.state
        if (
            self._snapshot.position_size_signed != 0.0
            and self._snapshot.stop_oid is None
        ):
            raise SolLiveStateError("cannot stop while exposure is unprotected")
        if state not in {SolLiveState.DISARMED, SolLiveState.FLAT, SolLiveState.OPEN}:
            raise SolLiveStateError(f"{state.value} cannot transition via stop")
        self._snapshot = replace(
            self._snapshot,
            state=SolLiveState.STOPPED,
            stop_reason=message,
        )

    def _require(self, expected: SolLiveState, operation: str) -> None:
        actual = self._snapshot.state
        if actual is not expected:
            raise SolLiveStateError(
                f"{actual.value} cannot perform {operation}; expected {expected.value}"
            )


def _oid(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SolLiveStateError(f"{label} must be a positive integer")
    return value


def _timestamp_ms(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolLiveStateError(f"{label} must be a nonnegative integer")
    return value


def _positive_price(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise SolLiveStateError(f"{label} must be positive and finite")
    return number


def _owned_position_snapshot(
    *,
    state: SolLiveState,
    entry_oid: int,
    stop_oid: int | None,
    position_size_signed: float,
    opened_at_ms: int,
    execution_plan: BoundExecutionPlan | None = None,
    target_oid: int | None = None,
    target_price: float | None = None,
) -> SolLiveSnapshot:
    size = float(position_size_signed)
    if size == 0.0:
        raise SolLiveStateError("restored position size must be nonzero")
    normalized_target_oid, normalized_target_price = _target_identity(
        target_oid,
        target_price,
    )
    return SolLiveSnapshot(
        state=state,
        entry_oid=_oid(entry_oid, "entry_oid"),
        stop_oid=None if stop_oid is None else _oid(stop_oid, "stop_oid"),
        position_size_signed=size,
        opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
        execution_plan=execution_plan,
        target_oid=normalized_target_oid,
        target_price=normalized_target_price,
    )


def _target_identity(
    target_oid: int | None,
    target_price: float | None,
) -> tuple[int | None, float | None]:
    if (target_oid is None) != (target_price is None):
        raise SolLiveStateError("target ownership requires both oid and price")
    if target_oid is None or target_price is None:
        return None, None
    return _oid(target_oid, "target_oid"), _positive_price(
        target_price,
        "target_price",
    )
