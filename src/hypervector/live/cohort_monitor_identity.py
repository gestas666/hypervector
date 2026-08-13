"""Fail-closed identity readers for read-only cohort monitor attachment."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
)


@dataclass(frozen=True)
class MonitorIdentity:
    """Authoritative run and profile identity used by monitor telemetry."""

    run_id: str
    profile_id: str
    profile_fingerprint: str


def active_ledger_identity(config: MultiAssetLiveConfig) -> MonitorIdentity:
    """Return an armed ledger identity matching the selected monitor profile."""
    record = _latest_configuration_identity(config.cohort_ledger)
    identity = _monitor_identity(record, "active ledger")
    if record.get("execution_mode") != "live" or record.get("live_armed") is not True:
        raise MultiAssetLiveConfigError("active ledger identity is not armed live")
    if (
        identity.profile_id != config.profile_id
        or identity.profile_fingerprint != config.profile_fingerprint
    ):
        raise MultiAssetLiveConfigError(
            "active ledger profile does not match --config; checkpoint recovery refused"
        )
    return identity


def checkpoint_identity(document: object) -> MonitorIdentity:
    """Return the complete live run identity from one checkpoint document."""
    if not isinstance(document, dict):
        raise MultiAssetLiveConfigError("recent checkpoint must be a JSON object")
    if document.get("mode") != "multi_asset_bidirectional_live_checkpoint":
        raise MultiAssetLiveConfigError("recent checkpoint mode is not live telemetry")
    audit = document.get("audit")
    if not isinstance(audit, dict):
        raise MultiAssetLiveConfigError(
            "recent checkpoint is missing live audit identity"
        )
    run = audit.get("run")
    if not isinstance(run, dict):
        raise MultiAssetLiveConfigError("recent checkpoint is missing run identity")
    return _monitor_identity(run, "recent checkpoint")


def require_staged_checkpoint_identity(
    document: object,
    active_config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig,
) -> None:
    """Require one checkpoint to carry the selected report-only next profile."""
    if not isinstance(document, dict):
        raise MultiAssetLiveConfigError("recent checkpoint must be a JSON object")
    generation = document.get("configuration_generation")
    if not isinstance(generation, dict):
        raise MultiAssetLiveConfigError(
            "recent checkpoint does not report the selected staged configuration"
        )
    matches_runtime = (
        active_config.profile_fingerprint == staged_config.profile_fingerprint
    )
    expected = {
        "runtime_profile_fingerprint": active_config.profile_fingerprint,
        "current_profile_fingerprint": staged_config.profile_fingerprint,
        "source_path": str(staged_config.source_path),
        "matches_runtime": matches_runtime,
        "state": (
            "current_runtime_configuration"
            if matches_runtime
            else "stale_runtime_configuration"
        ),
        "execution_authority": "none",
        "automatic_restart": False,
    }
    if any(generation.get(key) != value for key, value in expected.items()):
        raise MultiAssetLiveConfigError(
            "recent checkpoint staged configuration identity does not match "
            "--staged-config; refusing concurrent recovery"
        )


def require_matching_checkpoint_attachment(
    path: Path,
    active_config: MultiAssetLiveConfig,
    staged_config: MultiAssetLiveConfig | None = None,
) -> dict[str, object]:
    """Validate a checkpoint's identities without claiming that it is fresh."""
    try:
        active = active_ledger_identity(active_config)
    except MultiAssetLiveConfigError as exc:
        raise MultiAssetLiveConfigError(
            f"active checkpoint writer is not proven against the ledger: {exc}"
        ) from exc
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise MultiAssetLiveConfigError(
            f"active checkpoint writer is not identity-verifiable: {exc}"
        ) from exc
    checkpoint = checkpoint_identity(value)
    if checkpoint != active:
        raise MultiAssetLiveConfigError(
            "active checkpoint writer identity differs from the active ledger"
        )
    if staged_config is not None:
        require_staged_checkpoint_identity(value, active_config, staged_config)
    if not isinstance(value, dict):
        raise MultiAssetLiveConfigError("recent checkpoint must be a JSON object")
    return value


def _latest_configuration_identity(path: Path) -> dict[str, object]:
    latest: dict[str, object] | None = None
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if '"configuration_identity"' not in line:
                    continue
                latest = _decode_configuration_identity(line, path, line_number)
    except OSError as exc:
        raise MultiAssetLiveConfigError(
            f"active ledger is unavailable for checkpoint recovery: {path}: {exc}"
        ) from exc
    if latest is None:
        raise MultiAssetLiveConfigError(
            f"active ledger has no configuration identity: {path}"
        )
    return latest


def _decode_configuration_identity(
    line: str,
    path: Path,
    line_number: int,
) -> dict[str, object]:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MultiAssetLiveConfigError(
            f"active ledger identity is invalid at {path}:{line_number}"
        ) from exc
    if (
        not isinstance(value, dict)
        or value.get("event_type") != "configuration_identity"
    ):
        raise MultiAssetLiveConfigError(
            f"active ledger identity is malformed at {path}:{line_number}"
        )
    return value


def _monitor_identity(
    values: dict[str, object],
    source: str,
) -> MonitorIdentity:
    run_id = values.get("run_id")
    profile_id = values.get("profile_id")
    fingerprint = values.get("profile_fingerprint")
    identity = (run_id, profile_id, fingerprint)
    if not all(isinstance(value, str) and value.strip() for value in identity):
        raise MultiAssetLiveConfigError(f"{source} run/profile identity is invalid")
    return MonitorIdentity(str(run_id), str(profile_id), str(fingerprint))
