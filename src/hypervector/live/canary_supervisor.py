"""Fresh-ledger startup validation shared by staged canary supervisors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Protocol


class CanaryBackendProcess(Protocol):
    """Minimum child-process surface required during startup validation."""

    def poll(self) -> int | None:
        """Return the child exit code, or ``None`` while it is running."""
        ...


class CanarySupervisorError(RuntimeError):
    """A canary backend did not establish trustworthy fresh telemetry."""


@dataclass(frozen=True)
class LedgerStartupSnapshot:
    """Immutable append boundary and run identities present before launch."""

    initial_size: int
    prior_run_ids: frozenset[str]


def capture_ledger_start(path: Path) -> LedgerStartupSnapshot:
    """Validate and capture one ledger's state before starting a backend."""
    records = _json_records(path, offset=0, allow_incomplete=False)
    run_ids = frozenset(
        run_id
        for record in records
        if isinstance((run_id := record.get("run_id")), str) and run_id
    )
    return LedgerStartupSnapshot(initial_size=_file_size(path), prior_run_ids=run_ids)


def wait_for_fresh_configuration_identity(
    backend: CanaryBackendProcess,
    ledger: Path,
    *,
    snapshot: LedgerStartupSnapshot,
    expected_profile_fingerprint: str,
    expected_live_armed: bool,
    timeout_seconds: float,
    backend_label: str,
    log_path: Path,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Wait for a new run identity matching the requested profile and authority."""
    if timeout_seconds <= 0.0:
        raise CanarySupervisorError("startup timeout seconds must be positive")
    deadline = monotonic_fn() + timeout_seconds
    while monotonic_fn() < deadline:
        result = backend.poll()
        if result is not None:
            raise CanarySupervisorError(
                f"{backend_label} backend exited with {result} before fresh telemetry; "
                f"inspect {log_path}"
            )
        if _has_fresh_identity(
            ledger,
            snapshot=snapshot,
            expected_profile_fingerprint=expected_profile_fingerprint,
            expected_live_armed=expected_live_armed,
        ):
            return
        sleep_fn(0.05)
    raise CanarySupervisorError(
        f"{backend_label} backend telemetry not ready after {timeout_seconds:.1f}s; "
        f"inspect {log_path}"
    )


def _has_fresh_identity(
    path: Path,
    *,
    snapshot: LedgerStartupSnapshot,
    expected_profile_fingerprint: str,
    expected_live_armed: bool,
) -> bool:
    if _file_size(path) < snapshot.initial_size:
        raise CanarySupervisorError(
            f"canary ledger changed non-append-only during startup: {path}"
        )
    records = _json_records(path, offset=snapshot.initial_size, allow_incomplete=True)
    return any(
        _matches_identity(
            record,
            prior_run_ids=snapshot.prior_run_ids,
            expected_profile_fingerprint=expected_profile_fingerprint,
            expected_live_armed=expected_live_armed,
        )
        for record in records
    )


def _matches_identity(
    record: dict[str, object],
    *,
    prior_run_ids: frozenset[str],
    expected_profile_fingerprint: str,
    expected_live_armed: bool,
) -> bool:
    run_id = record.get("run_id")
    return (
        record.get("event_type") == "configuration_identity"
        and isinstance(run_id, str)
        and bool(run_id)
        and run_id not in prior_run_ids
        and record.get("profile_fingerprint") == expected_profile_fingerprint
        and record.get("live_armed") is expected_live_armed
    )


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _json_records(
    path: Path,
    *,
    offset: int,
    allow_incomplete: bool,
) -> list[dict[str, object]]:
    encoded = _read_bytes(path, offset)
    if not encoded:
        return []
    if not encoded.endswith(b"\n"):
        if allow_incomplete:
            return []
        raise CanarySupervisorError(f"canary ledger has an incomplete row: {path}")
    return _decode_records(encoded, path)


def _read_bytes(path: Path, offset: int) -> bytes:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read()
    except FileNotFoundError:
        return b""


def _decode_records(encoded: bytes, path: Path) -> list[dict[str, object]]:
    try:
        lines = encoded.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CanarySupervisorError(
            f"canary ledger is not valid UTF-8: {path}"
        ) from exc
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        records.append(_decode_record(line, line_number, path))
    return records


def _decode_record(line: str, line_number: int, path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CanarySupervisorError(
            f"canary ledger has invalid JSON row {line_number} at {path}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise CanarySupervisorError(
            f"canary ledger row {line_number} is not an object: {path}"
        )
    return value
