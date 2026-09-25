"""Immutable, hash-verified backups before a live cohort process starts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.cohort_backup_identity import (
    build_implementation_identity,
    implementation_identity_error,
)
from hypervector.live.cohort_prestart_ledger_sources import (
    CohortLedgerBackupPlan,
    CohortLedgerSourceError,
    build_cohort_ledger_backup_plan,
    previous_configuration_paths,
)

_CHUNK_BYTES = 1024 * 1024
# Level 6 compresses the ledgers about 1.8x faster than the gzip default of 9
# for about 6% more archive bytes (measured on the BTC ledger); restore
# verification is level-independent.
_COMPRESS_LEVEL = 6
# zlib and sha256 release the GIL, so the ledgers compress side by side. The
# cohort ledger alone bounds the wall time; more workers would not shorten it.
_ARCHIVE_WORKERS = 4
_MANIFEST_NAME = "manifest.json"
_SCHEMA_VERSION = 1
Record = Mapping[str, object]


class CohortPrestartBackupError(RuntimeError):
    """A live cohort backup could not be created or verified exactly."""


@dataclass(frozen=True)
class CohortPrestartBackupResult:
    """Published backup identity returned to the live startup boundary."""

    path: Path
    manifest_path: Path
    manifest_sha256: str
    strategy_changed: bool
    implementation_file_count: int
    implementation_sha256: str


@dataclass(frozen=True)
class _BackupSource:
    role: str
    path: Path


def create_cohort_prestart_backup(
    config: MultiAssetLiveConfig,
    *,
    now: datetime | None = None,
    implementation_sources: Mapping[str, Path] | None = None,
) -> CohortPrestartBackupResult:
    """Publish and verify a pre-start bundle before live clients are created."""
    if not implementation_sources:
        raise CohortPrestartBackupError("implementation sources are required")
    timestamp = _utc_timestamp(now or datetime.now(UTC))
    previous = _latest_configuration_identity(config.cohort_ledger)
    changed = _strategy_changed(previous, config.profile_fingerprint)
    _validate_previous_strategy_source(previous, config.source_path, changed)
    sources = _backup_sources(
        config,
        previous,
        changed,
        implementation_sources,
    )
    root = _backup_root(config)
    final = root / _bundle_name(timestamp, config.profile_fingerprint)
    root.mkdir(parents=True, exist_ok=True)
    if final.exists():
        raise CohortPrestartBackupError(f"backup bundle already exists: {final}")
    manifest = _manifest(config, previous, changed, timestamp)
    _publish_bundle(final, sources, manifest)
    verified = _published_manifest(final)
    identity = verified.get("implementation_identity")
    if not isinstance(identity, Mapping):
        raise CohortPrestartBackupError("verified implementation identity is missing")
    file_count = identity.get("file_count")
    sha256 = identity.get("sha256")
    if not isinstance(file_count, int) or not isinstance(sha256, str):
        raise CohortPrestartBackupError("verified implementation identity is invalid")
    return CohortPrestartBackupResult(
        path=final,
        manifest_path=final / _MANIFEST_NAME,
        manifest_sha256=_file_digest(final / _MANIFEST_NAME)[0],
        strategy_changed=bool(verified["strategy_changed"]),
        implementation_file_count=file_count,
        implementation_sha256=sha256,
    )


def verify_cohort_prestart_backup(bundle: Path | str) -> dict[str, object]:
    """Verify manifest structure and exact compressed/restored file hashes."""
    return _verified_manifest(Path(bundle), _verify_archive_record)


def _published_manifest(root: Path) -> dict[str, object]:
    """Check the structure of a bundle whose content was verified before its rename.

    The staging directory was fully verified (every archive re-hashed and
    restored) immediately before the same-directory rename that published it, and
    a rename does not change file contents, so a second full restore would only
    repeat that work. The external verifier still performs it on demand.
    """
    return _verified_manifest(root, _verify_archive_presence)


def _verified_manifest(
    root: Path, verify_record: Callable[[Path, object], None]
) -> dict[str, object]:
    manifest = _load_manifest(root / _MANIFEST_NAME)
    if manifest.get("schema_version") != _SCHEMA_VERSION:
        raise CohortPrestartBackupError("unsupported backup manifest schema")
    if manifest.get("bundle_type") != "cohort_prestart_backup":
        raise CohortPrestartBackupError("invalid backup manifest type")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise CohortPrestartBackupError("backup manifest has no file records")
    seen: set[str] = set()
    for record in records:
        relative = _record_archive_path(record)
        if relative in seen:
            raise CohortPrestartBackupError(f"duplicate backup archive: {relative}")
        seen.add(relative)
        verify_record(root, record)
    identity_error = implementation_identity_error(manifest, records)
    if identity_error is not None:
        raise CohortPrestartBackupError(identity_error)
    return manifest


def _backup_sources(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
    strategy_changed: bool,
    implementation_sources: Mapping[str, Path],
) -> tuple[_BackupSource, ...]:
    sources = [_required_source("target_config", config.source_path)]
    sources.extend(_ledger_sources(config, previous))
    sources.extend(_provider_sources(config))
    sources.extend(_previous_sources(previous, strategy_changed, config.source_path))
    if approval := config.transition_approval:
        sources.append(_required_source("transition_approval", approval))
    sources.extend(_optional_state_sources(config))
    sources.extend(
        _required_source(f"implementation_{role}", path)
        for role, path in sorted(implementation_sources.items())
    )
    return _unique_sources(sources)


def _ledger_sources(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
) -> list[_BackupSource]:
    plan = _ledger_backup_plan(config, previous)
    return [_required_source(role, path) for role, path in plan.source_pairs]


def _ledger_backup_plan(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
) -> CohortLedgerBackupPlan:
    try:
        return build_cohort_ledger_backup_plan(config, previous)
    except CohortLedgerSourceError as exc:
        raise CohortPrestartBackupError(str(exc)) from exc


def _provider_sources(config: MultiAssetLiveConfig) -> list[_BackupSource]:
    return [
        _required_source(
            f"target_provider_{provider.strategy_id}", provider.source_profile
        )
        for provider in config.providers
        if provider.source_profile is not None
    ]


def _previous_sources(
    previous: Mapping[str, object] | None,
    strategy_changed: bool,
    target_path: Path,
) -> list[_BackupSource]:
    if previous is None:
        return []
    paths = previous_configuration_paths(previous)
    sources: list[_BackupSource] = []
    for index, path in enumerate(paths):
        if not path.exists():
            if strategy_changed:
                raise CohortPrestartBackupError(
                    f"previous strategy source is missing: {path}"
                )
            continue
        role = "previous_config" if index == 0 else f"previous_provider_{index}"
        if path != target_path or strategy_changed:
            sources.append(_required_source(role, path))
    return sources


def _validate_previous_strategy_source(
    previous: Mapping[str, object] | None,
    target_path: Path,
    strategy_changed: bool,
) -> None:
    if previous is None or not strategy_changed:
        return
    paths = previous_configuration_paths(previous)
    if not paths:
        raise CohortPrestartBackupError("previous strategy source path is unavailable")
    previous_path = paths[0]
    if previous_path.resolve() == target_path.resolve():
        raise CohortPrestartBackupError(
            "strategy changes require a separate candidate file; "
            "the active config cannot be edited in place"
        )
    expected = previous.get("profile_fingerprint")
    if not isinstance(expected, str) or not expected:
        raise CohortPrestartBackupError("previous profile fingerprint is unavailable")
    try:
        observed = load_multi_asset_live_config(previous_path, mode="observe")
    except (FileNotFoundError, MultiAssetLiveConfigError, ValueError) as exc:
        raise CohortPrestartBackupError(
            f"previous strategy source cannot be validated: {previous_path}"
        ) from exc
    if observed.profile_fingerprint != expected:
        raise CohortPrestartBackupError(
            f"previous strategy source fingerprint mismatch: {previous_path}"
        )


def _optional_state_sources(config: MultiAssetLiveConfig) -> list[_BackupSource]:
    live_root = config.cohort_ledger.parent
    data_root = live_root.parents[1]
    runtime_root = data_root / "runtime" / live_root.name
    paths = sorted(runtime_root.glob("latest_*.json")) if runtime_root.exists() else []
    staged = live_root / "staged_profile.toml"
    if staged.is_file():
        paths.append(staged)
    sources = [
        _BackupSource(
            f"runtime_{path.stem}" if path.suffix == ".json" else "staged_profile", path
        )
        for path in paths
        if path.is_file()
    ]
    if (transition := live_root / "transition_drain.json").is_file():
        sources.append(_BackupSource("transition_drain", transition))
    return sources


def _unique_sources(sources: Sequence[_BackupSource]) -> tuple[_BackupSource, ...]:
    seen_roles: set[str] = set()
    unique: list[_BackupSource] = []
    for source in sources:
        if source.role in seen_roles:
            raise CohortPrestartBackupError(f"duplicate backup role: {source.role}")
        seen_roles.add(source.role)
        unique.append(source)
    return tuple(unique)


def _required_source(role: str, path: Path | None) -> _BackupSource:
    if path is None or not path.is_file():
        raise CohortPrestartBackupError(f"backup source is missing for {role}: {path}")
    return _BackupSource(role, path)


def _publish_bundle(
    final: Path,
    sources: Sequence[_BackupSource],
    manifest_base: dict[str, object],
) -> None:
    prefix = f".{final.name}."
    with tempfile.TemporaryDirectory(prefix=prefix, dir=final.parent) as raw_staging:
        staging = Path(raw_staging)
        records = _archive_sources(staging, sources)
        manifest = {**manifest_base, "files": records}
        identity = build_implementation_identity(records)
        if identity is not None:
            manifest["implementation_identity"] = identity
        _write_manifest(staging / _MANIFEST_NAME, manifest)
        verify_cohort_prestart_backup(staging)
        staging.rename(final)
        _fsync_directory(final.parent)


def _archive_sources(
    staging: Path, sources: Sequence[_BackupSource]
) -> list[dict[str, object]]:
    """Archive every source on parallel workers, returning records in source order."""
    with ThreadPoolExecutor(max_workers=_ARCHIVE_WORKERS) as pool:
        futures = [pool.submit(_archive_source, staging, source) for source in sources]
        try:
            return [future.result() for future in futures]
        except BaseException:
            for future in futures:
                future.cancel()
            raise


def _archive_source(staging: Path, source: _BackupSource) -> dict[str, object]:
    safe_role = _safe_role(source.role)
    relative = Path("files") / f"{safe_role}.gz"
    archive = staging / relative
    archive.parent.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256()
    source_bytes = 0
    with source.path.open("rb") as input_handle, archive.open("xb") as raw_output:
        with gzip.GzipFile(
            fileobj=raw_output, mode="wb", mtime=0, compresslevel=_COMPRESS_LEVEL
        ) as output:
            while chunk := input_handle.read(_CHUNK_BYTES):
                source_hash.update(chunk)
                source_bytes += len(chunk)
                output.write(chunk)
        raw_output.flush()
        os.fsync(raw_output.fileno())
    archive_hash, archive_bytes = _file_digest(archive)
    return {
        "role": source.role,
        "source_path": str(source.path),
        "archive_path": str(relative),
        "source_bytes": source_bytes,
        "source_sha256": source_hash.hexdigest(),
        "archive_bytes": archive_bytes,
        "archive_sha256": archive_hash,
    }


def _verify_archive_presence(root: Path, raw_record: object) -> None:
    if not isinstance(raw_record, Mapping):
        raise CohortPrestartBackupError("backup file record must be an object")
    archive = root / _record_archive_path(raw_record)
    if not archive.is_file():
        raise CohortPrestartBackupError(f"backup archive is missing: {archive}")
    if archive.stat().st_size != raw_record.get("archive_bytes"):
        raise CohortPrestartBackupError(f"archive byte count mismatch: {archive}")


def _verify_archive_record(root: Path, raw_record: object) -> None:
    if not isinstance(raw_record, Mapping):
        raise CohortPrestartBackupError("backup file record must be an object")
    relative = _record_archive_path(raw_record)
    archive = root / relative
    if not archive.is_file():
        raise CohortPrestartBackupError(f"backup archive is missing: {archive}")
    observed_hash, observed_bytes = _file_digest(archive)
    if observed_hash != raw_record.get("archive_sha256"):
        raise CohortPrestartBackupError(f"archive checksum mismatch: {archive}")
    if observed_bytes != raw_record.get("archive_bytes"):
        raise CohortPrestartBackupError(f"archive byte count mismatch: {archive}")
    restored_hash, restored_bytes = _gzip_digest(archive)
    if restored_hash != raw_record.get("source_sha256"):
        raise CohortPrestartBackupError(f"restored checksum mismatch: {archive}")
    if restored_bytes != raw_record.get("source_bytes"):
        raise CohortPrestartBackupError(f"restored byte count mismatch: {archive}")


def _record_archive_path(record: object) -> str:
    if not isinstance(record, Mapping):
        raise CohortPrestartBackupError("backup file record must be an object")
    relative = record.get("archive_path")
    if not isinstance(relative, str) or not relative:
        raise CohortPrestartBackupError("backup archive path is invalid")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise CohortPrestartBackupError(f"backup archive path is unsafe: {relative}")
    return relative


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _gzip_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with gzip.open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK_BYTES):
                digest.update(chunk)
                byte_count += len(chunk)
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise CohortPrestartBackupError(f"cannot restore backup: {path}") from exc
    return digest.hexdigest(), byte_count


def _latest_configuration_identity(path: Path) -> Mapping[str, object] | None:
    if not path.exists():
        return None
    latest: Mapping[str, object] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if '"event_type"' not in line or '"configuration_identity"' not in line:
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CohortPrestartBackupError(
                    f"invalid configuration identity at {path}:{line_number}"
                ) from exc
            if not isinstance(decoded, Mapping):
                raise CohortPrestartBackupError(
                    f"configuration identity is not an object at {path}:{line_number}"
                )
            if (
                decoded.get("execution_mode") == "observe"
                and decoded.get("live_armed") is False
            ):
                continue
            latest = decoded
    return latest


def _manifest(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
    changed: bool,
    timestamp: datetime,
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "bundle_type": "cohort_prestart_backup",
        "created_at_utc": timestamp.isoformat(),
        "execution_authority": "none",
        "strategy_changed": changed,
        "previous_identity": _identity_summary(previous),
        "target_identity": {
            "profile_id": config.profile_id,
            "profile_fingerprint": config.profile_fingerprint,
            "run_fingerprint": config.run_fingerprint,
            "config_source_path": str(config.source_path),
            "symbols": list(config.symbols),
        },
        "new_assets_without_prior_ledgers": _new_assets_without_prior_ledgers(
            config,
            previous,
        ),
        "restore_contract": "verify hashes before any explicit manual restore",
    }


def _new_assets_without_prior_ledgers(
    config: MultiAssetLiveConfig,
    previous: Mapping[str, object] | None,
) -> list[str]:
    return list(_ledger_backup_plan(config, previous).new_assets_without_prior_ledgers)


def _identity_summary(identity: Record | None) -> dict[str, object] | None:
    if identity is None:
        return None
    payload = identity.get("payload")
    config_source = (
        payload.get("config_source_path") if isinstance(payload, Mapping) else None
    )
    return {
        key: identity.get(key)
        for key in ("profile_id", "profile_fingerprint", "run_fingerprint", "run_id")
    } | {"config_source_path": config_source}


def _strategy_changed(previous: Record | None, target_fingerprint: str) -> bool:
    if previous is None:
        return False
    return previous.get("profile_fingerprint") != target_fingerprint


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CohortPrestartBackupError(f"cannot read manifest: {path}") from exc
    if not isinstance(decoded, dict):
        raise CohortPrestartBackupError("backup manifest must be an object")
    return decoded


def _write_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    try:
        text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
        encoded = text.encode()
    except (TypeError, ValueError) as exc:
        raise CohortPrestartBackupError("backup manifest is not JSON-safe") from exc
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _backup_root(config: MultiAssetLiveConfig) -> Path:
    live_root = config.cohort_ledger.parent
    data_root = live_root.parents[1]
    return data_root / "backups" / live_root.name


def _bundle_name(timestamp: datetime, profile_fingerprint: str) -> str:
    stamp = timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
    return f"prestart_{stamp}_{profile_fingerprint[:12]}"


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CohortPrestartBackupError("backup timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _safe_role(role: str) -> str:
    if not role or any(
        not (character.isalnum() or character in "_-") for character in role
    ):
        raise CohortPrestartBackupError(f"backup role is unsafe: {role!r}")
    return role


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
