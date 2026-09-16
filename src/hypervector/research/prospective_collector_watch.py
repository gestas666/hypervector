"""Finite, report-only observer with immutable start and terminal receipts."""

from collections.abc import Callable
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
import time

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json

Inspect = Callable[[], list[dict[str, object]]]


def run_health_watch(
    inspect: Inspect, output: Path, *, duration_seconds: float,
    interval_seconds: float = 15.0, monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Observe at startup and after every sleep, including the deadline sleep."""
    if not all(isfinite(value) and value > 0 for value in (duration_seconds, interval_seconds)):
        raise ValueError("watch duration and interval must be positive and finite")
    started = monotonic()
    deadline = started + duration_seconds
    write_immutable_json(output / "start.json", {
        "started_at_utc": datetime.now(UTC).isoformat(), "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds, "execution_authority": "none",
        "outcomes_evaluated": False, "automatic_restart": False,
    })
    cycles = 0
    while True:
        collectors = inspect()
        cycles += 1
        now = monotonic()
        status = _status(collectors, now >= deadline)
        report = {"observed_at_utc": datetime.now(UTC).isoformat(), "status": status,
                  "cycles": cycles, "elapsed_seconds": now - started, "collectors": collectors,
                  "execution_authority": "none", "outcomes_evaluated": False,
                  "automatic_restart": False}
        if cycles == 1:
            write_immutable_json(output / "initial.json", report)
        write_atomic_json(output / "latest.json", report)
        if status != "observing":
            write_immutable_json(output / "result.json", report)
            return report
        sleep(min(interval_seconds, max(0.0, deadline - now)))


def _status(collectors: list[dict[str, object]], deadline_reached: bool) -> str:
    if not collectors or any(row.get("status") not in {"healthy", "finished"} for row in collectors):
        return "alert"
    if all(row["status"] == "finished" for row in collectors):
        return "collection_finished"
    return "observation_deadline" if deadline_reached else "observing"
