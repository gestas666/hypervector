"""Cohort supervisor models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# Absolute so the exclusive lock, the restart journal and the process-lock probe
# cannot be split across two locations by the working directory of whatever
# process constructs SupervisorPaths().
LIVE_ROOT = REPOSITORY_ROOT / "data/live/bidirectional_cohort"
RUNTIME_ROOT = REPOSITORY_ROOT / "data/runtime/bidirectional_cohort"
RESEARCH_RUNTIME_ROOT = REPOSITORY_ROOT / "data/runtime/research"
BACKEND_MARKER = "multi_asset_bidirectional_live.py"
WEBHOOK_ENV = "HYPERVECTOR_ALERT_WEBHOOK_URL"
DEADMAN_ENV = "HYPERVECTOR_DEADMAN_URL"
EXIT_OPERATOR_STOP = 0
EXIT_START_REFUSED = 2
EXIT_STOP_INCOMPLETE = 5


@dataclass(frozen=True)
class SupervisorPaths:
    """Every file this process reads or appends. It truncates none of them."""

    ledger: Path = LIVE_ROOT / "decisions.jsonl"
    process_lock: Path = LIVE_ROOT / "process.lock"
    stop_file: Path = LIVE_ROOT / "STOP"
    checkpoint: Path = RUNTIME_ROOT / "latest_checkpoint.json"
    roster: Path = RESEARCH_RUNTIME_ROOT / "hip3_roster_latest.json"
    alerts: Path = RUNTIME_ROOT / "supervisor_alerts.jsonl"
    events: Path = RUNTIME_ROOT / "supervisor_events.jsonl"
    child_log: Path = RUNTIME_ROOT / "supervised_backend.log"


@dataclass(frozen=True)
class HealthThresholds:
    """Operator-set staleness limits. These alert; they never gate a trade."""

    heartbeat_seconds: float = 120.0
    checkpoint_seconds: float = 900.0
    roster_seconds: float = 900.0
    hip3_fee_bps: float = 1.5
    fee_lookback_hours: float = 24.0
    minimum_free_disk_gib: float = 10.0

    def __post_init__(self) -> None:
        """Reject unusable thresholds before any monitoring loop starts."""
        for label, value in asdict(self).items():
            require_positive(value, label)


@dataclass(frozen=True)
class RestartPolicy:
    """Bounded relaunch: exponential backoff inside a rolling budget."""

    maximum_restarts: int = 5
    window_seconds: float = 21_600.0
    initial_backoff_seconds: float = 30.0
    maximum_backoff_seconds: float = 900.0
    startup_grace_seconds: float = 1_800.0

    def __post_init__(self) -> None:
        """Validate an integral budget and finite, positive timing limits."""
        if type(self.maximum_restarts) is not int or self.maximum_restarts < 0:
            raise ValueError("maximum_restarts must be a nonnegative integer")
        for label, value in asdict(self).items():
            if label != "maximum_restarts":
                require_positive(value, label)
        if self.maximum_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("maximum backoff must be at least initial backoff")


def require_positive(value: float, label: str) -> None:
    """Reject nonfinite and nonpositive timing or measurement bounds."""
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")


@dataclass(frozen=True)
class HealthReport:
    """One read-only observation of the live system."""

    checked_at_utc: str
    backend_pid: int | None
    backend_alive: bool
    ledger_age_seconds: float | None
    checkpoint_age_seconds: float | None
    roster_age_seconds: float | None
    stop_file_present: bool
    maximum_hip3_fill_fee_bps: float | None
    hip3_fee_regime: dict[str, str] = field(default_factory=dict)
    free_disk_gib: float | None = None
    problems: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        """Return whether no alertable problem is present."""
        return not self.problems


@dataclass(frozen=True)
class RestartDecision:
    """What to do after the supervised process ended."""

    action: str  # "stop" | "hold" | "restart" | "give_up"
    reason: str
    delay_seconds: float = 0.0
