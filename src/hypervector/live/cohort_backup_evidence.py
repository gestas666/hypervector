"""Validated non-secret provenance for one verified cohort pre-start bundle."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult

_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_FIELDS = frozenset(
    {
        "status",
        "bundle_path",
        "manifest_path",
        "manifest_sha256",
        "strategy_changed",
        "implementation_file_count",
        "implementation_sha256",
    }
)


def prestart_backup_payload(
    backup: CohortPrestartBackupResult,
) -> dict[str, object]:
    """Serialize one verified backup result into bounded journal evidence."""
    raw: dict[str, object] = {
        "status": "verified",
        "bundle_path": str(backup.path),
        "manifest_path": str(backup.manifest_path),
        "manifest_sha256": backup.manifest_sha256,
        "strategy_changed": backup.strategy_changed,
        "implementation_file_count": backup.implementation_file_count,
        "implementation_sha256": backup.implementation_sha256,
    }
    validated = validated_prestart_backup_payload(raw)
    if validated is None:
        raise ValueError("verified pre-start backup evidence is unavailable")
    return validated


def validated_prestart_backup_payload(value: object) -> dict[str, object] | None:
    """Return normalized backup evidence or reject malformed provenance."""
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("pre-start backup evidence fields are invalid")
    bundle = _required_text(value.get("bundle_path"), "bundle path")
    manifest = _required_text(value.get("manifest_path"), "manifest path")
    if Path(manifest).parent != Path(bundle):
        raise ValueError("pre-start backup manifest must belong to its bundle")
    changed = value.get("strategy_changed")
    count = value.get("implementation_file_count")
    if value.get("status") != "verified" or not isinstance(changed, bool):
        raise ValueError("pre-start backup verification status is invalid")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("pre-start backup implementation count is invalid")
    manifest_hash = _required_hash(value.get("manifest_sha256"), "manifest")
    implementation_hash = _required_hash(
        value.get("implementation_sha256"), "implementation"
    )
    return {
        "status": "verified",
        "bundle_path": bundle,
        "manifest_path": manifest,
        "manifest_sha256": manifest_hash,
        "strategy_changed": changed,
        "implementation_file_count": count,
        "implementation_sha256": implementation_hash,
    }


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pre-start backup {label} is invalid")
    return value.strip()


def _required_hash(value: object, label: str) -> str:
    text = _required_text(value, f"{label} SHA-256")
    if _HASH_PATTERN.fullmatch(text) is None:
        raise ValueError(f"pre-start backup {label} SHA-256 is invalid")
    return text
