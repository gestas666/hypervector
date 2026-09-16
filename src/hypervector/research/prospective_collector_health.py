"""Passive process, source and heartbeat checks for frozen research collectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from hypervector.data.oxa_storage import file_evidence
from hypervector.runtime_lock import cohort_checkpoint_writer_active

MAX_HEARTBEAT_AGE_MS = 120_000
FUTURE_TOLERANCE_MS = 5000
_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_PROCESS_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class CollectorPin:
    """Immutable collector identity established outside the observation loop."""

    label: str
    root: Path
    pid: int
    process: str
    manifest_sha256: str
    cadence_ms: int

    def __post_init__(self) -> None:
        if not self.label or not self.process or not self.root.is_absolute():
            raise ValueError("collector requires label, process identity and absolute root")
        if type(self.pid) is not int or self.pid <= 0:
            raise ValueError("collector PID must be a positive integer")
        if type(self.cadence_ms) is not int or self.cadence_ms <= 0:
            raise ValueError("collector cadence must be a positive integer")
        if len(self.manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.manifest_sha256):
            raise ValueError("collector manifest SHA256 must be lowercase hexadecimal")


def read_document(path: Path) -> tuple[dict[str, object], str]:
    """Read a bounded JSON object and authenticate the exact parsed bytes."""
    with path.open("rb") as handle:
        raw = handle.read(_MAX_DOCUMENT_BYTES + 1)
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"collector document exceeds size limit: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"collector document must be an object: {path}")
    return value, sha256(raw).hexdigest()


def load_pins(path: Path) -> tuple[CollectorPin, ...]:
    """Load complete explicit identities, rejecting empty or ambiguous inputs."""
    document, _ = read_document(path)
    rows = document.get("collectors")
    if not isinstance(rows, list) or not rows:
        raise ValueError("pin file requires a nonempty collectors list")
    pins = tuple(_pin(row) for row in rows)
    for field in ("label", "pid", "root"):
        if len({getattr(pin, field) for pin in pins}) != len(pins):
            raise ValueError(f"duplicate collector {field} in pin file")
    return pins


def _pin(row: object) -> CollectorPin:
    fields = {"label", "root", "pid", "process", "manifest_sha256", "cadence_ms"}
    if not isinstance(row, dict) or set(row) != fields:
        raise ValueError("collector pin requires exactly its six identity fields")
    if any(not isinstance(row[key], str) for key in ("label", "root", "process", "manifest_sha256")):
        raise ValueError("collector identity text fields must be strings")
    return CollectorPin(row["label"], Path(row["root"]), row["pid"], row["process"],
                        row["manifest_sha256"], row["cadence_ms"])


def process_identity(pid: int) -> str | None:
    """Read process birth and command without signalling the process."""
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart=,command="],
                            capture_output=True, text=True, timeout=_PROCESS_TIMEOUT_SECONDS,
                            check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return None
    result.check_returncode()
    return result.stdout.strip()


def lock_owners(path: Path) -> set[int]:
    """Read the processes holding this lock file open; occupancy is checked too."""
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-F", "p", "--", str(path)],
                            capture_output=True, text=True, timeout=_PROCESS_TIMEOUT_SECONDS,
                            check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return set()
    result.check_returncode()
    return {int(line[1:]) for line in result.stdout.splitlines() if line.startswith("p")}


def observe_collector(pin: CollectorPin, *, now_ms: int | None = None) -> dict[str, object]:
    """Return retained alert evidence on invalid/missing sources or runtime state."""
    report: dict[str, object] = {"label": pin.label, "pid": pin.pid,
                                 "execution_authority": "none", "outcomes_evaluated": False}
    try:
        manifest = _manifest(pin)
        payload, digest = read_document(pin.root / "latest.json")
        now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
        status = _validate_health(payload, manifest, pin, now)
        report.update(health_sha256=digest, health_snapshot=payload, heartbeat_ms=payload["heartbeat_ms"],
                      observed_ms=now, state=payload["state"], status=status)
        identity = process_identity(pin.pid)
        if status != "finished":
            if identity != pin.process:
                raise ValueError("collector process is absent or its birth/command changed")
            if lock_owners(pin.root / "latest.json.writer.lock") != {pin.pid}:
                raise ValueError("collector writer lock has missing or unexpected open-file owners")
            if not cohort_checkpoint_writer_active(pin.root / "latest.json"):
                raise ValueError("collector writer lock is unoccupied")
        report["process_observed"] = identity
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        report.update(status="alert", reason=f"{type(exc).__name__}: {exc}")
    return report


def _manifest(pin: CollectorPin) -> dict[str, object]:
    manifest, digest = read_document(pin.root / "manifest.json")
    if digest != pin.manifest_sha256:
        raise ValueError("frozen collector manifest SHA256 changed")
    _authority(manifest)
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] not in (1, 2):
        raise ValueError("unsupported frozen collector schema")
    sources = manifest.get("collector_sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("manifest has no pinned collector sources")
    for source in [*sources, manifest.get("protocol")]:
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            raise ValueError("manifest source evidence must contain a path")
        path = Path(source["path"])
        evidence = file_evidence(path)
        if not path.is_absolute() or any(evidence[key] != source.get(key) for key in ("bytes", "sha256")):
            raise ValueError(f"frozen source/protocol changed: {path}")
    return manifest


def _authority(payload: dict[str, object]) -> None:
    if payload.get("execution_authority") != "none" or payload.get("automatic_promotion") is not False:
        raise ValueError("collector authority contract changed")


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _timestamp(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("collector timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("collector timestamp requires timezone")
    return round(parsed.timestamp() * 1000)


def _validate_health(payload: dict[str, object], manifest: dict[str, object], pin: CollectorPin, now: int) -> str:
    _authority(payload)
    if payload.get("outcomes_evaluated") is not False or "error" not in payload or payload["error"] is not None:
        raise ValueError("collector reports an error or changed outcome seal")
    if _integer(payload.get("schema_version"), "schema") != manifest.get("schema_version"):
        raise ValueError("collector health schema differs from frozen manifest")
    if _integer(payload.get("pid"), "health PID") != pin.pid:
        raise ValueError("health PID differs from pinned process")
    heartbeat = _integer(payload.get("heartbeat_ms"), "heartbeat")
    if _timestamp(payload.get("generated_at_utc")) != heartbeat:
        raise ValueError("collector heartbeat timestamps disagree")
    if heartbeat > now + FUTURE_TOLERANCE_MS:
        raise ValueError("collector heartbeat is in the future")
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("manifest requires a study contract")
    start, end = (_integer(contract.get(key), key) for key in ("start_ms", "end_ms"))
    if start >= end or _timestamp(payload.get("study_start_utc")) != start or _timestamp(payload.get("study_end_exclusive_utc")) != end:
        raise ValueError("collector study window differs from frozen manifest")
    phase = "before_start" if heartbeat < start else "collecting" if heartbeat < end else "collection_window_ended"
    if payload.get("study_phase") != phase:
        raise ValueError("collector study phase disagrees with heartbeat")
    if payload.get("state") == "finished":
        cycle = payload.get("last_cycle")
        if heartbeat < end or not isinstance(cycle, dict) or cycle.get("completed_boundary_ms") != end:
            raise ValueError("collector finished without evidence of the final boundary")
        return "finished"
    if payload.get("state") not in {"waiting", "capturing"}:
        raise ValueError(f"unexpected collector state: {payload.get('state')}")
    if now - heartbeat > MAX_HEARTBEAT_AGE_MS:
        raise ValueError("collector heartbeat exceeded 120 seconds")
    if payload["state"] == "waiting":
        due = _integer(payload.get("next_due_ms"), "next due")
        if not heartbeat <= due <= heartbeat + pin.cadence_ms + FUTURE_TOLERANCE_MS:
            raise ValueError("collector waiting schedule is invalid")
    return "healthy"
