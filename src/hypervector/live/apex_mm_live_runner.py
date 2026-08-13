"""Continuous polling and clean shutdown for the Apex MM canary."""

from __future__ import annotations

from collections.abc import Callable
import math
from pathlib import Path
import time
from typing import Protocol

from hyperliquid.utils.error import ClientError  # type: ignore[import-untyped]

from hypervector.live.apex_mm_live_models import ApexMMLiveSnapshot, ApexMMLiveState

_RATE_LIMIT_BACKOFF_SECONDS = (10.0, 20.0, 30.0, 30.0)


class ApexMMLiveRunnerError(RuntimeError):
    """The Apex MM live loop cannot start safely."""


class ApexMMLiveRunnerEngineProtocol(Protocol):
    """Lifecycle operations required by the polling loop."""

    @property
    def cleanup_required(self) -> bool:
        """Return whether live venue mutations still require verified cleanup."""
        ...

    def start(self) -> ApexMMLiveSnapshot:
        """Complete fail-closed venue preflight and begin quoting."""
        ...

    def process(self) -> ApexMMLiveSnapshot:
        """Reconcile venue facts and advance one quote cycle."""
        ...

    def shutdown(self) -> ApexMMLiveSnapshot:
        """Cancel, flatten, and verify the account is flat."""
        ...


class ApexMMLiveRunner:
    """Poll an explicitly armed Apex MM engine until a bounded stop."""

    def __init__(
        self,
        *,
        engine: ApexMMLiveRunnerEngineProtocol,
        stop_file: Path,
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
            raise ApexMMLiveRunnerError("poll_seconds must be positive and finite")
        self._engine = engine
        self._stop_file = stop_file
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._monotonic_fn = monotonic_fn

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until operator stop, fault, or optional bounded completion."""
        _validate_max_polls(max_polls)
        if self._stop_file.exists():
            raise ApexMMLiveRunnerError(
                f"live stop file already exists; remove intentionally: {self._stop_file}"
            )
        polls = 0
        try:
            snapshot = self._engine.start()
            if snapshot.state is ApexMMLiveState.FAULT:
                return polls
            while not self._stop_file.exists():
                cycle_started = self._monotonic_fn()
                snapshot = self._retry_rate_limit(self._engine.process)
                polls += 1
                if snapshot.state is ApexMMLiveState.FAULT:
                    break
                if max_polls is not None and polls >= max_polls:
                    break
                elapsed = self._monotonic_fn() - cycle_started
                if (remaining := self._poll_seconds - elapsed) > 0.0:
                    self._sleep_fn(remaining)
            return polls
        finally:
            if self._engine.cleanup_required:
                self._retry_rate_limit(self._engine.shutdown)

    def _retry_rate_limit(
        self,
        operation: Callable[[], ApexMMLiveSnapshot],
    ) -> ApexMMLiveSnapshot:
        """Retry only explicit HTTP 429 failures with bounded venue backoff."""
        for attempt in range(len(_RATE_LIMIT_BACKOFF_SECONDS) + 1):
            try:
                return operation()
            except ClientError as exc:
                exhausted = attempt == len(_RATE_LIMIT_BACKOFF_SECONDS)
                if exc.status_code != 429 or exhausted:
                    raise
                self._sleep_fn(_RATE_LIMIT_BACKOFF_SECONDS[attempt])
        raise AssertionError("rate-limit recovery exhausted without returning")


def _validate_max_polls(value: int | None) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise ApexMMLiveRunnerError("max_polls must be a positive integer")
