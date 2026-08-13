"""Content identity for execution implementation files in live backups."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

_ROLE_PREFIX = "implementation_"


def build_implementation_identity(
    records: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    """Return a stable composite hash for implementation archive records."""
    components = sorted(
        (_identity_component(record) for record in records if _is_source(record)),
        key=lambda component: str(component["role"]),
    )
    if not components:
        return None
    encoded = json.dumps(
        components,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return {
        "algorithm": "sha256",
        "file_count": len(components),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def implementation_identity_error(
    manifest: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
) -> str | None:
    """Return why a declared implementation identity does not reconcile."""
    expected = build_implementation_identity(records)
    declared = manifest.get("implementation_identity")
    if expected is None and declared is None:
        return None
    if expected is None:
        return "implementation identity exists without implementation files"
    if not isinstance(declared, Mapping):
        return "implementation identity is missing or invalid"
    if dict(declared) != expected:
        return "implementation identity checksum mismatch"
    return None


def _is_source(record: Mapping[str, object]) -> bool:
    role = record.get("role")
    return isinstance(role, str) and role.startswith(_ROLE_PREFIX)


def _identity_component(record: Mapping[str, object]) -> dict[str, object]:
    return {key: record.get(key) for key in ("role", "source_bytes", "source_sha256")}
