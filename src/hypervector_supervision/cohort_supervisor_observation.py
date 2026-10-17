"""Injected clocks and adoption monitoring for cohort supervision."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import signal
import time

from hypervector_supervision.cohort_supervisor_models import (
    SupervisorPaths,
    HealthThresholds,
)
from hypervector_supervision.cohort_supervisor_health import (
    evaluate_health,
    process_is_backend,
)
from hypervector_supervision.cohort_supervisor_alerts import (
    Alerter,
    ping_deadman,
)
from hypervector_supervision.cohort_supervisor_host import (
    BootIdentity,
    previous_shutdown_epoch,
    read_boot_identity,
)


class _StopFlag:
    """Set by SIGTERM/SIGINT so the loop can forward a graceful stop."""

    def __init__(self) -> None:
        self.requested = False

    def install(self) -> None:
        """Translate operator signals into graceful stop requests."""
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, self._handle)

    def _handle(self, _number: int, _frame: object) -> None:
        self.requested = True


@dataclass
class SupervisorRuntime:
    """Injected clocks and hooks so the loop is testable without real waits."""

    now: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    is_backend: Callable[[int], bool] = process_is_backend
    deadman: Callable[[str | None], None] = ping_deadman
    # Read once when supervision starts; a reboot ends this process.
    boot_identity: Callable[[], BootIdentity] = read_boot_identity
    # Called only while deciding an opt-in resume after a host restart.
    previous_shutdown: Callable[[float], float | None] = previous_shutdown_epoch


def wait_for_adopted_exit(
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    alerter: Alerter,
    stop: _StopFlag,
    runtime: SupervisorRuntime,
    *,
    interval: float,
    deadman_url: str | None,
) -> bool:
    """Watch an already-running backend. Return True once it has ended."""
    while not stop.requested:
        now = runtime.now()
        report = evaluate_health(
            paths, thresholds, now=now, is_backend=runtime.is_backend
        )
        alerter.observe(report, now)
        runtime.deadman(deadman_url)
        if not report.backend_alive:
            return True
        runtime.sleep(interval)
    return False
