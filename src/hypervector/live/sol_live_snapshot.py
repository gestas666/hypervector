"""Immutable lifecycle values shared by execution, recovery and telemetry."""

from dataclasses import dataclass
from enum import Enum

from hypervector.live.cohort_execution_plan import BoundExecutionPlan
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)


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
    protective_progress: ProtectiveExecutionProgress = ProtectiveExecutionProgress()

    def as_payload(self) -> dict[str, object]:
        """Serialize the complete durable ownership and execution-progress contract."""
        return {
            "state": self.state.value,
            "entry_oid": self.entry_oid,
            "stop_oid": self.stop_oid,
            "target_oid": self.target_oid,
            "close_oid": self.close_oid,
            "position_size_signed": self.position_size_signed,
            "opened_at_ms": self.opened_at_ms,
            "last_fault": self.last_fault,
            "stop_reason": self.stop_reason,
            "execution_plan": (
                self.execution_plan.as_payload() if self.execution_plan is not None else None
            ),
            "target_price": self.target_price,
            "protective_progress": self.protective_progress.as_payload(),
        }
