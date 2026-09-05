"""Fail-closed approval and replacement lineage for cohort profile changes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from pathlib import Path

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

Record = Mapping[str, object]
RouteScope = tuple[str, str, str]
RetirementMapping = tuple[RouteScope, RouteScope | None]

_DOCUMENT_TYPE = "cohort_profile_change_approval"
_LIVE_STATUS = "approved_for_live_transition"
_HEADER_FIELDS = {
    "schema_version",
    "document_type",
    "approval_status",
    "approved_at_utc",
    "approved_by",
    "operator_approval",
    "execution_authority",
    "previous_profile",
    "candidate_profile",
    "change_scopes",
    "recommendation_evidence",
    "rollback",
    "retirements",
}


class ProfileChangeApprovalError(ValueError):
    """A changed cohort profile lacks exact operator-approved lineage."""


def previous_transition_identity(
    backup: CohortPrestartBackupResult,
) -> tuple[str, str]:
    """Return the prior profile and run identities from a verified backup."""
    previous = _verified_backup_manifest(backup).get("previous_identity")
    profile = _previous_value(previous, "profile_fingerprint")
    run_id = _previous_value(previous, "run_id")
    if profile is None or run_id is None:
        raise CohortTransitionDrainError(
            "changed profile lacks prior run identity in verified backup"
        )
    return profile, run_id


def require_approved_profile_change(
    config: MultiAssetLiveConfig,
    backup: CohortPrestartBackupResult,
) -> dict[str, object] | None:
    """Require exact approval for a changed profile before client construction."""
    if not backup.strategy_changed:
        return None
    prior_config = previous_profile_config(config, backup)
    return validate_profile_change_approval(
        prior_config,
        config,
        config.transition_approval,
    )


def previous_profile_config(
    config: MultiAssetLiveConfig,
    backup: CohortPrestartBackupResult,
) -> MultiAssetLiveConfig:
    """Load the prior config authenticated by the verified pre-start backup."""
    previous = _verified_backup_manifest(backup).get("previous_identity")
    source = _previous_value(previous, "config_source_path")
    expected = _previous_value(previous, "profile_fingerprint")
    if source is None:
        raise ProfileChangeApprovalError(
            "changed profile lacks previous config source in verified backup"
        )
    prior_config = load_multi_asset_live_config(Path(source), mode="observe")
    if prior_config.profile_fingerprint != expected:
        raise ProfileChangeApprovalError(
            "previous config differs from verified backup identity"
        )
    return prior_config


def validate_profile_change_approval(
    previous: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
    approval_path: Path | None,
) -> dict[str, object]:
    """Validate exact change approval without granting order authority."""
    removed = previous.executable_provider_directions.difference(
        candidate.executable_provider_directions
    )
    if previous.profile_fingerprint == candidate.profile_fingerprint:
        return _unchanged_evidence(removed)
    if approval_path is None:
        raise ProfileChangeApprovalError(
            "changed profile requires an exact approval document"
        )
    document = _load_document(approval_path)
    _validate_header(document)
    _validate_profile_identity(document, previous, candidate)
    _verify_recommendation_evidence(document, approval_path.parent)
    _verify_rollback(document, approval_path.parent, previous)
    replacements = _validate_retirements(document, previous, candidate)
    return {
        "state": "approved_profile_change",
        "approval_required": True,
        "approval_status": _LIVE_STATUS,
        "approval_document": str(approval_path),
        "retired_execution_scopes": _scope_labels(removed),
        "replacement_execution_scopes": _scope_labels(replacements),
        "execution_authority": "none",
    }


def _verified_backup_manifest(
    backup: CohortPrestartBackupResult,
) -> dict[str, object]:
    try:
        encoded = backup.manifest_path.read_bytes()
    except OSError as exc:
        raise CohortTransitionDrainError(
            "verified backup manifest cannot be read"
        ) from exc
    if hashlib.sha256(encoded).hexdigest() != backup.manifest_sha256:
        raise CohortTransitionDrainError("verified backup manifest checksum changed")
    try:
        manifest = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise CohortTransitionDrainError(
            "verified backup manifest JSON is invalid"
        ) from exc
    if not isinstance(manifest, dict):
        raise CohortTransitionDrainError("verified backup manifest must be an object")
    return manifest


def _previous_value(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) and candidate else None


def _unchanged_evidence(removed: set[RouteScope]) -> dict[str, object]:
    if removed:
        raise ProfileChangeApprovalError(
            "unchanged profile fingerprint cannot contain retired scopes"
        )
    return {
        "state": "unchanged_profile",
        "approval_required": False,
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "none",
    }


def _load_document(path: Path) -> Record:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileChangeApprovalError(
            f"approval document does not exist: {path}"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileChangeApprovalError("approval document is unreadable") from exc
    return _record(raw, "approval document")


def _validate_header(document: Record) -> None:
    missing = sorted(_HEADER_FIELDS.difference(document))
    unknown = sorted(set(document).difference(_HEADER_FIELDS))
    if missing or unknown:
        raise ProfileChangeApprovalError(
            f"approval document fields are invalid: missing={missing}, unknown={unknown}"
        )
    if document.get("schema_version") != 1:
        raise ProfileChangeApprovalError("approval schema_version must be 1")
    if document.get("document_type") != _DOCUMENT_TYPE:
        raise ProfileChangeApprovalError("approval document_type is invalid")
    if document.get("approval_status") != _LIVE_STATUS:
        raise ProfileChangeApprovalError(
            "approval status is not approved_for_live_transition"
        )
    if document.get("execution_authority") != "none":
        raise ProfileChangeApprovalError("approval must not grant execution authority")
    _text(document.get("approved_by"), "approved_by")
    _text(document.get("operator_approval"), "operator_approval")
    _aware_timestamp(document.get("approved_at_utc"))
    _text_sequence(document.get("change_scopes"), "change_scopes")


def _validate_profile_identity(
    document: Record,
    previous: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
) -> None:
    prior = _profile_identity(document.get("previous_profile"), "previous")
    target = _profile_identity(document.get("candidate_profile"), "candidate")
    if prior[0] != previous.profile_id:
        raise ProfileChangeApprovalError("previous profile id differs from approval")
    if prior[1] != previous.profile_fingerprint:
        raise ProfileChangeApprovalError(
            "previous profile fingerprint differs from approval"
        )
    if target[0] != candidate.profile_id:
        raise ProfileChangeApprovalError("candidate profile id differs from approval")
    if target[1] != candidate.profile_fingerprint:
        raise ProfileChangeApprovalError(
            "candidate profile fingerprint differs from approval"
        )


def _profile_identity(value: object, label: str) -> tuple[str, str]:
    row = _record(value, f"{label} profile")
    _require_exact_fields(row, {"profile_id", "profile_fingerprint"}, label)
    return (
        _text(row.get("profile_id"), f"{label} profile id"),
        _sha256_text(
            row.get("profile_fingerprint"),
            f"{label} profile fingerprint",
        ),
    )


def _verify_recommendation_evidence(document: Record, root: Path) -> None:
    rows = _records(
        document.get("recommendation_evidence"),
        "recommendation_evidence",
    )
    if not rows:
        raise ProfileChangeApprovalError("recommendation_evidence must not be empty")
    for row in rows:
        _require_exact_fields(row, {"path", "sha256"}, "recommendation evidence")
        path = _source_path(root, row.get("path"), "recommendation evidence")
        expected = _sha256_text(row.get("sha256"), "recommendation evidence sha256")
        if _file_sha256(path) != expected:
            raise ProfileChangeApprovalError("recommendation evidence sha256 differs")


def _verify_rollback(
    document: Record,
    root: Path,
    previous: MultiAssetLiveConfig,
) -> None:
    rollback = _record(document.get("rollback"), "rollback")
    fields = {"config_path", "profile_fingerprint", "sha256"}
    _require_exact_fields(rollback, fields, "rollback")
    path = _source_path(root, rollback.get("config_path"), "rollback config")
    expected_sha = _sha256_text(rollback.get("sha256"), "rollback sha256")
    if _file_sha256(path) != expected_sha:
        raise ProfileChangeApprovalError("rollback config sha256 differs")
    expected_profile = _sha256_text(
        rollback.get("profile_fingerprint"),
        "rollback profile fingerprint",
    )
    if expected_profile != previous.profile_fingerprint:
        raise ProfileChangeApprovalError("rollback profile fingerprint is not previous")
    _verify_rollback_profile(path, expected_profile)


def _verify_rollback_profile(path: Path, expected_fingerprint: str) -> None:
    try:
        rollback = load_multi_asset_live_config(path, mode="observe")
    except (FileNotFoundError, MultiAssetLiveConfigError, ValueError) as exc:
        raise ProfileChangeApprovalError("rollback config cannot be loaded") from exc
    if rollback.profile_fingerprint != expected_fingerprint:
        raise ProfileChangeApprovalError("rollback config profile identity differs")


def _validate_retirements(
    document: Record,
    previous: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
) -> set[RouteScope]:
    removed = previous.executable_provider_directions.difference(
        candidate.executable_provider_directions
    )
    added = candidate.executable_provider_directions.difference(
        previous.executable_provider_directions
    )
    rows = _records(document.get("retirements"), "retirements")
    mappings = tuple(_retirement_mapping(row) for row in rows)
    mapped_removed = [retired for retired, _ in mappings]
    replacements = [
        replacement for _, replacement in mappings if replacement is not None
    ]
    if len(set(mapped_removed)) != len(mapped_removed):
        raise ProfileChangeApprovalError("retirement scopes must be unique")
    if set(mapped_removed) != removed:
        raise ProfileChangeApprovalError(
            "retirement mappings differ from removed execution scopes"
        )
    _require_replacements(mappings, added)
    return set(replacements)


def _retirement_mapping(value: Record) -> RetirementMapping:
    _require_exact_fields(
        value,
        {"retired_scope", "replacement_scope"},
        "retirement",
    )
    retired = _route_scope(value.get("retired_scope"), "retired")
    raw_replacement = value.get("replacement_scope")
    replacement = (
        None
        if raw_replacement is None
        else _route_scope(raw_replacement, "replacement")
    )
    return retired, replacement


def _route_scope(value: object, label: str) -> RouteScope:
    row = _record(value, f"{label} scope")
    _require_exact_fields(row, {"strategy_id", "symbol", "side"}, label)
    scope = (
        _text(row.get("strategy_id"), f"{label} strategy_id"),
        _text(row.get("symbol"), f"{label} symbol"),
        _text(row.get("side"), f"{label} side"),
    )
    if scope[2] not in {"long", "short"}:
        raise ProfileChangeApprovalError(f"{label} side is invalid")
    return scope


def _require_replacements(
    mappings: Sequence[RetirementMapping],
    added: set[RouteScope],
) -> None:
    replacements = [
        replacement for _, replacement in mappings if replacement is not None
    ]
    if len(set(replacements)) != len(replacements):
        raise ProfileChangeApprovalError("replacement scopes must be unique")
    for retired, replacement in mappings:
        if replacement is None:
            continue
        if retired[1:] != replacement[1:]:
            raise ProfileChangeApprovalError(
                "replacement must preserve retired symbol and side"
            )
        if replacement not in added:
            raise ProfileChangeApprovalError(
                "replacement scope must be newly added by candidate"
            )


def _require_exact_fields(value: Record, expected: set[str], label: str) -> None:
    missing = sorted(expected.difference(value))
    unknown = sorted(set(value).difference(expected))
    if missing or unknown:
        raise ProfileChangeApprovalError(
            f"{label} fields are invalid: missing={missing}, unknown={unknown}"
        )


def _source_path(root: Path, value: object, label: str) -> Path:
    raw = Path(_text(value, f"{label} path"))
    path = raw if raw.is_absolute() else root / raw
    if not path.is_file():
        raise ProfileChangeApprovalError(f"{label} file does not exist: {path}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ProfileChangeApprovalError(
            f"cannot hash approval source: {path}"
        ) from exc
    return digest.hexdigest()


def _scope_labels(scopes: set[RouteScope]) -> list[str]:
    return ["|".join(scope) for scope in sorted(scopes)]


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ProfileChangeApprovalError(f"{label} must be an array")
    return tuple(_record(row, label) for row in value)


def _record(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ProfileChangeApprovalError(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ProfileChangeApprovalError(f"{label} keys must be text")
    return value


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ProfileChangeApprovalError(f"{label} must be a non-empty text array")
    return tuple(_text(item, label) for item in value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileChangeApprovalError(f"{label} must be non-empty text")
    return value.strip()


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ProfileChangeApprovalError(f"{label} must be a sha256 hex digest")
    return text


def _aware_timestamp(value: object) -> datetime:
    raw = _text(value, "approved_at_utc")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileChangeApprovalError("approved_at_utc is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileChangeApprovalError("approved_at_utc must include a timezone")
    return parsed
