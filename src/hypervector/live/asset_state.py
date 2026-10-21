"""Pure per-symbol execution-state contract for the live lifecycle."""

from __future__ import annotations

from dataclasses import replace
import math

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.asset_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)
from hypervector.live.asset_live_snapshot import (
    AssetLiveSnapshot,
    AssetLiveState,
    AssetLiveStateError,
)


class AssetLiveStateMachine:
    """Enforce protection, flat-before-entry, and restart invariants."""

    def __init__(self) -> None:
        self._snapshot = AssetLiveSnapshot()

    @property
    def snapshot(self) -> AssetLiveSnapshot:
        """Return the current immutable lifecycle snapshot."""
        return self._snapshot

    def begin_preflight(self) -> None:
        """Move a disarmed process into read/reconcile-only preflight."""
        self._require(AssetLiveState.DISARMED, "begin_preflight")
        self._snapshot = replace(self._snapshot, state=AssetLiveState.PREFLIGHT)

    def confirm_preflight_flat(self) -> None:
        """Confirm venue reconciliation found no exposure or orders for the symbol."""
        self._require(AssetLiveState.PREFLIGHT, "confirm_preflight_flat")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

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
        protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
    ) -> None:
        """Restore only an owned, venue-verified position and protective stop."""
        self._require(AssetLiveState.PREFLIGHT, "restore_protected_position")
        size = float(position_size_signed)
        if size == 0.0:
            raise AssetLiveStateError("restored position size must be nonzero")
        self._snapshot = _owned_position_snapshot(
            state=AssetLiveState.OPEN,
            entry_oid=entry_oid,
            stop_oid=stop_oid,
            target_oid=target_oid,
            position_size_signed=size,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
            protective_progress=protective_progress,
            target_price=target_price,
        )

    def restore_pending_entry(
        self,
        *,
        entry_oid: int,
        execution_plan: BoundExecutionPlan | None = None,
        protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
    ) -> None:
        """Restore a venue-verified committed entry before adding protection."""
        self._require(AssetLiveState.PREFLIGHT, "restore_pending_entry")
        self._snapshot = AssetLiveSnapshot(
            state=AssetLiveState.ENTRY_PENDING,
            entry_oid=_oid(entry_oid, "entry_oid"),
            execution_plan=execution_plan,
            protective_progress=protective_progress,
        )

    def restore_protecting_position(
        self,
        *,
        entry_oid: int,
        position_size_signed: float,
        opened_at_ms: int,
        execution_plan: BoundExecutionPlan | None = None,
        protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
    ) -> None:
        """Restore venue exposure whose committed stop is being recovered."""
        self._require(AssetLiveState.PREFLIGHT, "restore_protecting_position")
        self._snapshot = _owned_position_snapshot(
            state=AssetLiveState.PROTECTING,
            entry_oid=entry_oid,
            stop_oid=None,
            position_size_signed=position_size_signed,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
            protective_progress=protective_progress,
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
        protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
    ) -> None:
        """Restore exact ownership while a committed close is resolved."""
        self._require(AssetLiveState.PREFLIGHT, "restore_exit_pending")
        self._snapshot = _owned_position_snapshot(
            state=AssetLiveState.EXIT_PENDING,
            entry_oid=entry_oid,
            stop_oid=stop_oid,
            position_size_signed=position_size_signed,
            opened_at_ms=opened_at_ms,
            execution_plan=execution_plan,
            protective_progress=protective_progress,
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
        protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
    ) -> None:
        """Restore protected exposure whose target mutation is unresolved."""
        self._require(AssetLiveState.PREFLIGHT, "restore_target_pending")
        size = float(position_size_signed)
        if size == 0.0:
            raise AssetLiveStateError("restored position size must be nonzero")
        self._snapshot = AssetLiveSnapshot(
            state=AssetLiveState.TARGET_PENDING,
            entry_oid=_oid(entry_oid, "entry_oid"),
            stop_oid=_oid(stop_oid, "stop_oid"),
            position_size_signed=size,
            opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
            execution_plan=execution_plan,
            protective_progress=protective_progress,
            target_price=_positive_price(target_price, "target_price"),
        )

    def begin_entry(
        self,
        *,
        execution_plan: BoundExecutionPlan | None = None,
    ) -> None:
        """Reserve the sole entry slot from a verified-flat state."""
        self._require(AssetLiveState.FLAT, "begin_entry")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.ENTRY_PENDING,
            execution_plan=execution_plan,
        )

    def acknowledge_entry(self, entry_oid: int) -> None:
        """Attach the venue order ID without claiming an actual fill."""
        self._require(AssetLiveState.ENTRY_PENDING, "acknowledge_entry")
        self._snapshot = replace(self._snapshot, entry_oid=_oid(entry_oid, "entry_oid"))

    def confirm_entry_not_filled(self) -> None:
        """Release an unfilled entry slot only after venue-flat verification."""
        self._require(AssetLiveState.ENTRY_PENDING, "confirm_entry_not_filled")
        if self._snapshot.entry_oid is not None or self._snapshot.position_size_signed:
            raise AssetLiveStateError("unfilled entry cannot retain venue ownership")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def begin_protection(
        self,
        *,
        position_size_signed: float,
        opened_at_ms: int,
    ) -> None:
        """Record reconciled exposure before submitting its venue stop."""
        self._require(AssetLiveState.ENTRY_PENDING, "begin_protection")
        if self._snapshot.entry_oid is None:
            raise AssetLiveStateError(
                "entry acknowledgement is required before protection"
            )
        size = float(position_size_signed)
        if size == 0.0:
            raise AssetLiveStateError("protected position size must be nonzero")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.PROTECTING,
            position_size_signed=size,
            opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
        )

    def confirm_protection(self, *, stop_oid: int) -> None:
        """Mark exposure open only after a stop has a venue order ID."""
        self._require(AssetLiveState.PROTECTING, "confirm_protection")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.OPEN,
            stop_oid=_oid(stop_oid, "stop_oid"),
        )

    def begin_target(self, *, stop_oid: int, target_price: float) -> None:
        """Persist stop ownership before submitting a required target."""
        self._require(AssetLiveState.PROTECTING, "begin_target")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.TARGET_PENDING,
            stop_oid=_oid(stop_oid, "stop_oid"),
            target_price=_positive_price(target_price, "target_price"),
        )

    def confirm_target(self, *, target_oid: int) -> None:
        """Report OPEN only after the complete bracket is venue-visible."""
        self._require(AssetLiveState.TARGET_PENDING, "confirm_target")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.OPEN,
            target_oid=_oid(target_oid, "target_oid"),
        )

    def confirm_target_fill_during_protection(self, *, target_oid: int) -> None:
        """Clear exposure when a new target fills before OPEN is emitted."""
        self._require(AssetLiveState.TARGET_PENDING, "confirm_target_fill")
        _oid(target_oid, "target_oid")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def confirm_protective_stop_fill_during_protection(self, *, stop_oid: int) -> None:
        """Clear exposure when the exact new stop fills before becoming OPEN."""
        self._require(AssetLiveState.PROTECTING, "confirm_stop_fill")
        _oid(stop_oid, "stop_oid")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def confirm_protective_stop_fill_during_exit(self, *, stop_oid: int) -> None:
        """Clear residual exposure when its replacement stop fills during exit."""
        self._require(AssetLiveState.EXIT_PENDING, "confirm_stop_fill_during_exit")
        _oid(stop_oid, "stop_oid")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def begin_exit(self) -> None:
        """Reserve the lifecycle for exact stop cancellation and close."""
        self._require(AssetLiveState.OPEN, "begin_exit")
        if self._snapshot.stop_oid is None:
            raise AssetLiveStateError("open position has no known protective stop")
        self._snapshot = replace(self._snapshot, state=AssetLiveState.EXIT_PENDING)

    def confirm_protective_stop_fill(self, *, stop_oid: int) -> None:
        """Clear OPEN only after the venue reports the exact owned stop fill."""
        self._require(AssetLiveState.OPEN, "confirm_protective_stop_fill")
        observed = _oid(stop_oid, "stop_oid")
        if self._snapshot.stop_oid != observed:
            raise AssetLiveStateError(
                f"protective stop fill oid {observed} does not match owned stop"
            )
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def confirm_owned_bracket_exit(self) -> None:
        """Clear OPEN after an exact owned bracket lifecycle reconciles flat."""
        if self._snapshot.state not in {
            AssetLiveState.OPEN,
            AssetLiveState.EXIT_PENDING,
        }:
            raise AssetLiveStateError(
                f"{self._snapshot.state.value} cannot confirm owned bracket exit"
            )
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def begin_target_after_exit_failure(self, *, target_price: float) -> None:
        """Restore target placement while retaining the original venue stop."""
        self._require(AssetLiveState.EXIT_PENDING, "begin_target_after_exit_failure")
        if self._snapshot.stop_oid is None:
            raise AssetLiveStateError("target restoration requires an owned stop")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.TARGET_PENDING,
            target_oid=None,
            target_price=_positive_price(target_price, "target_price"),
            close_oid=None,
        )

    def replace_protection(self, *, stop_oid: int) -> None:
        """Swap the owned stop identity for a raised venue stop while staying OPEN."""
        self._require(AssetLiveState.OPEN, "replace_protection")
        if self._snapshot.stop_oid is None:
            raise AssetLiveStateError("protection replacement requires an owned stop")
        self._snapshot = replace(self._snapshot, stop_oid=_oid(stop_oid, "stop_oid"))

    def acknowledge_close(self, close_oid: int) -> None:
        """Attach the reduce-only close order ID pending flat reconciliation."""
        self._require(AssetLiveState.EXIT_PENDING, "acknowledge_close")
        self._snapshot = replace(self._snapshot, close_oid=_oid(close_oid, "close_oid"))

    def restore_protection_after_exit_failure(self, *, stop_oid: int) -> None:
        """Return to OPEN after a failed close is re-protected at the venue."""
        self._require(
            AssetLiveState.EXIT_PENDING, "restore_protection_after_exit_failure"
        )
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.OPEN,
            stop_oid=_oid(stop_oid, "stop_oid"),
            close_oid=None,
        )

    def acknowledge_partial_close(self, *, position_size_signed: float) -> None:
        """Persist a verified same-direction remainder while retaining its original clock."""
        self._require(AssetLiveState.EXIT_PENDING, "acknowledge_partial_close")
        previous = self._snapshot.position_size_signed
        remaining = position_size_signed
        if (
            self._snapshot.close_oid is None
            or isinstance(remaining, bool)
            or not math.isfinite(remaining)
            or remaining * previous <= 0.0
            or abs(remaining) >= abs(previous)
        ):
            raise AssetLiveStateError(
                "partial close requires an acknowledged exact reduction"
            )
        self._snapshot = replace(self._snapshot, position_size_signed=remaining)

    def acknowledge_protective_execution(
        self, *, position_size_signed: float, progress: ProtectiveExecutionProgress
    ) -> None:
        """Retain proved partial receipts, original ownership and any required stop exit."""
        before = self._snapshot
        old = before.protective_progress
        size = position_size_signed
        if (
            before.state not in {AssetLiveState.OPEN, AssetLiveState.EXIT_PENDING}
            or isinstance(size, bool)
            or not math.isfinite(size)
            or size == 0
            or (size > 0) != (before.position_size_signed > 0)
            or abs(size) >= abs(before.position_size_signed)
            or len(progress.fills) <= len(old.fills)
            or progress.fills[: len(old.fills)] != old.fills
            or (old.stop_exit_required and not progress.stop_exit_required)
        ):
            raise AssetLiveStateError(
                "protective execution requires a cumulative owned reduction"
            )
        executed = math.fsum(fill.size for fill in progress.fills[len(old.fills) :])
        if not math.isclose(
            executed,
            abs(before.position_size_signed) - abs(size),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise AssetLiveStateError(
                "protective execution receipts mismatch the remaining size"
            )
        self._snapshot = replace(
            before,
            position_size_signed=size,
            protective_progress=progress,
            close_oid=None,
            state=AssetLiveState.EXIT_PENDING
            if progress.stop_exit_required
            else AssetLiveState.OPEN,
        )

    def confirm_flat(self) -> None:
        """Clear order identity only after venue reconciliation verifies flat."""
        self._require(AssetLiveState.EXIT_PENDING, "confirm_flat")
        if self._snapshot.close_oid is None:
            raise AssetLiveStateError("close acknowledgement is required before flat")
        self._snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT)

    def fault(self, reason: str) -> None:
        """Enter an explicit fault while preserving known venue identity."""
        message = reason.strip()
        if not message:
            raise AssetLiveStateError("fault reason must be non-empty")
        if self._snapshot.state is AssetLiveState.STOPPED:
            raise AssetLiveStateError("STOPPED cannot transition via fault")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.FAULTED,
            last_fault=message,
        )

    def stop(self, reason: str) -> None:
        """Stop without removing a known venue-native protective order."""
        message = reason.strip()
        if not message:
            raise AssetLiveStateError("stop reason must be non-empty")
        state = self._snapshot.state
        if (
            self._snapshot.position_size_signed != 0.0
            and self._snapshot.stop_oid is None
        ):
            raise AssetLiveStateError("cannot stop while exposure is unprotected")
        if state not in {AssetLiveState.DISARMED, AssetLiveState.FLAT, AssetLiveState.OPEN}:
            raise AssetLiveStateError(f"{state.value} cannot transition via stop")
        self._snapshot = replace(
            self._snapshot,
            state=AssetLiveState.STOPPED,
            stop_reason=message,
        )

    def _require(self, expected: AssetLiveState, operation: str) -> None:
        actual = self._snapshot.state
        if actual is not expected:
            raise AssetLiveStateError(
                f"{actual.value} cannot perform {operation}; expected {expected.value}"
            )


def _oid(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AssetLiveStateError(f"{label} must be a positive integer")
    return value


def _timestamp_ms(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AssetLiveStateError(f"{label} must be a nonnegative integer")
    return value


def _positive_price(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise AssetLiveStateError(f"{label} must be positive and finite")
    return number


def _owned_position_snapshot(
    *,
    state: AssetLiveState,
    entry_oid: int,
    stop_oid: int | None,
    position_size_signed: float,
    opened_at_ms: int,
    execution_plan: BoundExecutionPlan | None = None,
    target_oid: int | None = None,
    target_price: float | None = None,
    protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress(),
) -> AssetLiveSnapshot:
    size = float(position_size_signed)
    if size == 0.0:
        raise AssetLiveStateError("restored position size must be nonzero")
    normalized_target_oid, normalized_target_price = _target_identity(
        target_oid,
        target_price,
    )
    return AssetLiveSnapshot(
        state=state,
        entry_oid=_oid(entry_oid, "entry_oid"),
        stop_oid=None if stop_oid is None else _oid(stop_oid, "stop_oid"),
        position_size_signed=size,
        opened_at_ms=_timestamp_ms(opened_at_ms, "opened_at_ms"),
        execution_plan=execution_plan,
        protective_progress=protective_progress,
        target_oid=normalized_target_oid,
        target_price=normalized_target_price,
    )


def _target_identity(
    target_oid: int | None,
    target_price: float | None,
) -> tuple[int | None, float | None]:
    if (target_oid is None) != (target_price is None):
        raise AssetLiveStateError("target ownership requires both oid and price")
    if target_oid is None or target_price is None:
        return None, None
    return _oid(target_oid, "target_oid"), _positive_price(
        target_price,
        "target_price",
    )
