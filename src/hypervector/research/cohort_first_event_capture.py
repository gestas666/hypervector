"""Immutable report-only capture contracts for a cohort's first live event."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Literal

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_first_event_trigger import (
    build_first_event_observations,
)

Record = Mapping[str, object]
CaptureStage = Literal["first_event", "resolved_lifecycle"]

_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "runtime_strategy_changed": False,
}


@dataclass(frozen=True)
class FirstEventTrigger:
    """Validated source-bound state for one first-event hypothesis."""

    hypothesis_id: str
    identity: dict[str, str]
    baseline_path: Path
    observation: dict[str, object]

    @property
    def requires_capture(self) -> bool:
        """Return whether the source trigger requires immediate evidence."""
        return _boolean(
            self.observation.get("requires_immediate_audit"),
            "requires immediate audit",
        )


@dataclass(frozen=True)
class CapturePaths:
    """Deterministic immutable paths for one first-event evidence bundle."""

    directory: Path
    after_audit: Path
    delta: Path
    manifest: Path


def build_capture_trigger(
    checkpoint: Record,
    overrides: Record,
    hypothesis_id: str,
) -> FirstEventTrigger:
    """Validate contracts and build one exact first-event trigger state."""
    _validate_contract(checkpoint.get("checkpoint_contract"), "checkpoint")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    _validate_contract(audit.get("experiment_contract"), "audit")
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError("first-event capture requires the current runtime profile")
    identity = _identity(_mapping(audit.get("run"), "audit run"))
    _validate_override_identity(overrides, identity)
    hypothesis = _select_hypothesis(overrides, hypothesis_id)
    observation = build_first_event_observations(audit, (hypothesis,))[0]
    baseline_path = Path(_text(hypothesis.get("evidence_baseline"), "baseline path"))
    return FirstEventTrigger(hypothesis_id, identity, baseline_path, observation)


def capture_required(trigger: FirstEventTrigger, stage: CaptureStage) -> bool:
    """Return whether the requested immutable capture milestone is present."""
    _require_capture_stage(stage)
    if stage == "first_event":
        return trigger.requires_capture
    deltas = _mapping(trigger.observation.get("counter_deltas"), "counter deltas")
    return _count(deltas.get("closed_trades"), "closed-trade delta") > 0


def capture_waiting_state(stage: CaptureStage) -> str:
    """Return the bounded status state for an unmet capture milestone."""
    _require_capture_stage(stage)
    if stage == "resolved_lifecycle":
        return "awaiting_resolved_lifecycle"
    return "awaiting_first_event"


def capture_paths(
    out_dir: Path,
    trigger: FirstEventTrigger,
    capture_stage: CaptureStage = "first_event",
) -> CapturePaths:
    """Resolve deterministic artifact paths for a trigger and run identity."""
    _require_capture_stage(capture_stage)
    stem = f"{_slug(trigger.hypothesis_id)}_{_slug(trigger.identity['run_id'])}"
    if capture_stage == "resolved_lifecycle":
        stem = f"{stem}_resolved_lifecycle"
    directory = out_dir / stem
    return CapturePaths(
        directory=directory,
        after_audit=directory / "after_audit.json",
        delta=directory / "delta.json",
        manifest=directory / "manifest.json",
    )


def validate_audit(path: Path, identity: Record) -> None:
    """Require an immutable after-prefix audit for the exact active run."""
    _validate_audit(path, identity, "after audit")


def validate_baseline(path: Path, identity: Record) -> None:
    """Require the frozen baseline to remain present and identity-compatible."""
    _validate_audit(path, identity, "baseline audit")


def validate_delta(path: Path, identity: Record) -> None:
    """Require a report-only delta for the exact active run."""
    delta = _load(path, "audit delta")
    _validate_contract(delta.get("contract"), "audit delta")
    _require_identity(_mapping(delta.get("identity"), "delta identity"), identity)


def build_manifest(
    trigger: FirstEventTrigger,
    *,
    checkpoint_path: Path,
    overrides_path: Path,
    paths: CapturePaths,
    capture_stage: CaptureStage = "first_event",
) -> dict[str, object]:
    """Build the immutable, source-hashed first-event capture manifest."""
    _require_capture_stage(capture_stage)
    return {
        "schema_version": 1,
        "mode": "cohort_first_event_immutable_capture",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "contract": dict(_CONTRACT),
        "hypothesis_id": trigger.hypothesis_id,
        "capture_stage": capture_stage,
        "identity": dict(trigger.identity),
        "trigger": dict(trigger.observation),
        "source_evidence": {
            "checkpoint": _evidence(checkpoint_path),
            "decision_overrides": _evidence(overrides_path),
            "baseline_audit": _evidence(trigger.baseline_path),
            "after_audit": _evidence(paths.after_audit),
            "delta": _evidence(paths.delta),
        },
    }


def validate_manifest(
    path: Path,
    trigger: FirstEventTrigger,
    capture_stage: CaptureStage = "first_event",
) -> Record:
    """Validate a prior capture before treating the watcher as idempotent."""
    _require_capture_stage(capture_stage)
    manifest = _load(path, "capture manifest")
    _validate_contract(manifest.get("contract"), "capture manifest")
    if manifest.get("hypothesis_id") != trigger.hypothesis_id:
        raise ValueError("capture manifest hypothesis identity mismatch")
    if manifest.get("capture_stage", "first_event") != capture_stage:
        raise ValueError("capture manifest stage mismatch")
    _require_identity(
        _mapping(manifest.get("identity"), "manifest identity"), trigger.identity
    )
    evidence = _mapping(manifest.get("source_evidence"), "manifest evidence")
    _require_evidence(evidence.get("after_audit"), path.parent / "after_audit.json")
    _require_evidence(evidence.get("delta"), path.parent / "delta.json")
    return manifest


def status_payload(
    trigger: FirstEventTrigger,
    *,
    state: str,
    manifest_path: Path | None = None,
    capture_stage: CaptureStage = "first_event",
) -> dict[str, object]:
    """Build one bounded mutable watcher status payload."""
    _require_capture_stage(capture_stage)
    payload: dict[str, object] = {
        "schema_version": 1,
        "mode": "cohort_first_event_capture_status",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "state": state,
        "contract": dict(_CONTRACT),
        "hypothesis_id": trigger.hypothesis_id,
        "capture_stage": capture_stage,
        "identity": dict(trigger.identity),
        "trigger_status": trigger.observation.get("status"),
        "requires_immediate_audit": trigger.requires_capture,
    }
    if manifest_path is not None:
        payload["manifest_path"] = str(manifest_path)
        payload["manifest_evidence"] = _evidence(manifest_path)
    return payload


def _validate_override_identity(overrides: Record, identity: Record) -> None:
    _validate_contract(overrides.get("contract"), "decision overrides")
    if overrides.get("source_profile_id") != identity.get("profile_id"):
        raise ValueError("decision override profile identity mismatch")
    if overrides.get("source_profile_fingerprint") != identity.get(
        "profile_fingerprint"
    ):
        raise ValueError("decision override profile fingerprint mismatch")


def _validate_audit(path: Path, identity: Record, label: str) -> None:
    audit = _load(path, label)
    _validate_contract(audit.get("experiment_contract"), label)
    _require_identity(_mapping(audit.get("run"), f"{label} run"), identity)


def _select_hypothesis(overrides: Record, hypothesis_id: str) -> Record:
    rows = _sequence(overrides.get("active_hypotheses"), "active hypotheses")
    matches = [
        _mapping(row, "active hypothesis")
        for row in rows
        if isinstance(row, Mapping) and row.get("hypothesis_id") == hypothesis_id
    ]
    if len(matches) != 1:
        raise ValueError("first-event hypothesis must match exactly once")
    return matches[0]


def _validate_contract(value: object, label: str) -> None:
    contract = _mapping(value, f"{label} contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(
        contract.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError(f"{label} contract is not report-only")


def _require_identity(observed: Record, expected: Record) -> None:
    for field in ("run_id", "profile_id", "profile_fingerprint"):
        if observed.get(field) != expected.get(field):
            raise ValueError(f"capture artifact {field} mismatch")


def _identity(value: Record) -> dict[str, str]:
    return {
        field: _text(value.get(field), field)
        for field in ("run_id", "profile_id", "profile_fingerprint")
    }


def _evidence(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"capture evidence is missing: {path}")
    return {"path": str(path), **file_evidence(path)}


def _require_evidence(value: object, path: Path) -> None:
    expected = _mapping(value, f"evidence {path.name}")
    observed = file_evidence(path)
    if expected.get("sha256") != observed["sha256"]:
        raise ValueError(f"capture evidence checksum mismatch: {path}")
    if expected.get("bytes") != observed["bytes"]:
        raise ValueError(f"capture evidence byte count mismatch: {path}")


def _load(path: Path, label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    return _mapping(json.loads(path.read_text()), label)


def _slug(value: str) -> str:
    output = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-")
    if not output:
        raise ValueError("capture identity cannot produce an empty path")
    return output


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _require_capture_stage(stage: str) -> None:
    if stage not in {"first_event", "resolved_lifecycle"}:
        raise ValueError("capture stage must be first_event or resolved_lifecycle")
