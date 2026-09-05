"""Continuous supervisor for the report-only SOL route-native replay."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Protocol

from requests.exceptions import RequestException

from hypervector.research.sol_route_native_one_blocker_command import (
    FundingEvidenceFetcher,
    fetch_official_sol_funding_evidence,
    run_sol_route_native_snapshot,
)


@dataclass(frozen=True)
class SolRouteNativeMonitorSpec:
    """Immutable local paths and frozen identity for the SOL evidence monitor."""

    config_path: Path
    cohort_ledger: Path
    asset_ledger: Path
    data_root: Path
    source_run_id: str
    capture_start_ms: int
    output: Path

    def __post_init__(self) -> None:
        """Reject missing experiment identity before touching evidence."""
        if not self.source_run_id.strip():
            raise ValueError("SOL monitor source run id must be non-empty")
        if self.capture_start_ms <= 0:
            raise ValueError("SOL monitor capture start must be positive")


class SnapshotRunner(Protocol):
    """Callable boundary for one evidence-bound snapshot refresh."""

    def __call__(
        self,
        *,
        config_path: Path,
        cohort_ledger: Path,
        asset_ledger: Path,
        data_root: Path,
        source_run_id: str,
        capture_start_ms: int,
        observed_at_ms: int,
        output: Path,
        funding_fetcher: FundingEvidenceFetcher,
    ) -> dict[str, object]:
        """Build and publish one bounded snapshot."""


def run_sol_route_native_monitor(
    *,
    spec: SolRouteNativeMonitorSpec,
    once: bool,
    interval_seconds: float,
    archive_lag_seconds: float,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    funding_fetcher: FundingEvidenceFetcher = fetch_official_sol_funding_evidence,
    snapshot_runner: SnapshotRunner = run_sol_route_native_snapshot,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Refresh bounded snapshots while preserving the last good report on error."""
    _validate_monitor_inputs(spec, interval_seconds, archive_lag_seconds)
    while True:
        observed_at_ms = int(clock_ms() - archive_lag_seconds * 1_000)
        if observed_at_ms <= spec.capture_start_ms:
            raise ValueError("SOL monitor observation must follow capture start")
        try:
            report = snapshot_runner(
                config_path=spec.config_path,
                cohort_ledger=spec.cohort_ledger,
                asset_ledger=spec.asset_ledger,
                data_root=spec.data_root,
                source_run_id=spec.source_run_id,
                capture_start_ms=spec.capture_start_ms,
                observed_at_ms=observed_at_ms,
                output=spec.output,
                funding_fetcher=funding_fetcher,
            )
        except (OSError, ValueError, RuntimeError, RequestException) as exc:
            _emit_monitor_event("refresh_failed", observed_at_ms, str(exc))
            if once:
                return 2
        else:
            _emit_monitor_event(str(report.get("status")), observed_at_ms, None)
            if once:
                return 0
        sleep_fn(interval_seconds)


def _validate_monitor_inputs(
    spec: SolRouteNativeMonitorSpec,
    interval_seconds: float,
    archive_lag_seconds: float,
) -> None:
    if not math.isfinite(interval_seconds) or interval_seconds <= 0.0:
        raise ValueError("SOL monitor interval must be finite and positive")
    if not math.isfinite(archive_lag_seconds) or archive_lag_seconds < 0.0:
        raise ValueError("SOL monitor archive lag must be finite and nonnegative")
    output = spec.output.resolve()
    inputs = (spec.config_path, spec.cohort_ledger, spec.asset_ledger)
    if any(path.resolve() == output for path in inputs):
        raise ValueError("SOL monitor output must differ from every input")


def _emit_monitor_event(status: str, observed_at_ms: int, error: str | None) -> None:
    payload: dict[str, object] = {
        "event_type": "v51_sol_route_native_one_blocker_refresh",
        "status": status,
        "observed_at_utc": _iso(observed_at_ms),
        "execution_authority": "none",
    }
    if error is not None:
        payload["error"] = error
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def _iso(timestamp_ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp_ms / 1_000))
