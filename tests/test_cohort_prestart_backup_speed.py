"""The pre-start bundle is faster without changing what it proves.

Level-9 gzip of every ledger in sequence, plus a second full verification of the
already-verified bundle after its rename, took about three minutes of every armed
start. Archives now use level 6 on parallel workers, in the same manifest order,
and the bundle is fully verified exactly once, before it gets its final name.
"""

from __future__ import annotations

from datetime import UTC, datetime
import gzip
import hashlib
import json
from pathlib import Path
import threading
import time

import pytest

from test_cohort_prestart_backup import (
    _implementation_sources,
    _seed_state,
    _write_config,
)

from hypervector.live import cohort_prestart_backup as backup
from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    create_cohort_prestart_backup,
    verify_cohort_prestart_backup,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_NOW = datetime(2026, 9, 24, 16, tzinfo=UTC)


def _config(tmp_path: Path) -> object:
    previous = _write_config(tmp_path, profile="previous-profile")
    target = _write_config(tmp_path, profile="target-profile")
    decisions = _seed_state(tmp_path, previous)
    with decisions.open("a", encoding="utf-8") as handle:
        for index in range(2_000):
            handle.write(json.dumps({"sequence": index, "event_type": "heartbeat"}))
            handle.write("\n")
    return load_multi_asset_live_config(
        target, mode="live", enabled=True, accepts_live_risk=True
    )


def _bundles(tmp_path: Path) -> list[Path]:
    root = tmp_path / "data/backups/bidirectional_cohort"
    return sorted(root.iterdir()) if root.exists() else []


def test_archives_are_level_six_and_restore_exact_bytes(tmp_path: Path) -> None:
    config = _config(tmp_path)

    result = create_cohort_prestart_backup(
        config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
    )

    manifest = verify_cohort_prestart_backup(result.path)
    for record in manifest["files"]:
        archive = result.path / record["archive_path"]
        # Byte 8 of a gzip member is XFL: 2 marks level 9, 0 any middle level.
        assert archive.read_bytes()[8] == 0
        with gzip.open(archive, "rb") as handle:
            restored = handle.read()
        assert hashlib.sha256(restored).hexdigest() == record["source_sha256"]
        assert Path(record["source_path"]).read_bytes() == restored


def test_parallel_archiving_keeps_the_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow first archive cannot reorder the manifest or its identity."""
    config = _config(tmp_path)
    original_archive = backup._archive_source
    original_publish = backup._publish_bundle
    submitted: list[str] = []
    threads: set[int] = set()

    def slow_first(staging: Path, source: object) -> dict[str, object]:
        threads.add(threading.get_ident())
        if source.role == "target_config":  # type: ignore[attr-defined]
            time.sleep(0.2)
        return original_archive(staging, source)  # type: ignore[arg-type]

    def capture(final: Path, sources: object, manifest: object) -> None:
        submitted.extend(source.role for source in sources)  # type: ignore[attr-defined]
        original_publish(final, sources, manifest)  # type: ignore[arg-type]

    monkeypatch.setattr(backup, "_archive_source", slow_first)
    monkeypatch.setattr(backup, "_publish_bundle", capture)

    result = create_cohort_prestart_backup(
        config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [record["role"] for record in manifest["files"]] == submitted
    assert submitted[0] == "target_config"
    assert len(threads) > 1


def test_a_failed_archive_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    original_archive = backup._archive_source

    def fail_one(staging: Path, source: object) -> dict[str, object]:
        if source.role == "cohort_ledger":  # type: ignore[attr-defined]
            raise OSError("disk full")
        return original_archive(staging, source)  # type: ignore[arg-type]

    monkeypatch.setattr(backup, "_archive_source", fail_one)

    with pytest.raises(OSError, match="disk full"):
        create_cohort_prestart_backup(
            config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
        )

    assert _bundles(tmp_path) == []


def test_a_corrupt_staged_archive_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The single verification still gates the rename."""
    config = _config(tmp_path)
    original_archive = backup._archive_source

    def corrupt(staging: Path, source: object) -> dict[str, object]:
        record = original_archive(staging, source)  # type: ignore[arg-type]
        if record["role"] == "cohort_ledger":
            archive = staging / str(record["archive_path"])
            archive.write_bytes(archive.read_bytes() + b"x")
        return record

    monkeypatch.setattr(backup, "_archive_source", corrupt)

    with pytest.raises(CohortPrestartBackupError, match="archive checksum mismatch"):
        create_cohort_prestart_backup(
            config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
        )

    assert _bundles(tmp_path) == []


def test_the_bundle_is_fully_verified_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    restored: list[Path] = []
    original_digest = backup._gzip_digest

    def counting(path: Path) -> tuple[str, int]:
        restored.append(path)
        return original_digest(path)

    monkeypatch.setattr(backup, "_gzip_digest", counting)

    result = create_cohort_prestart_backup(
        config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert len(restored) == len(manifest["files"])
    assert result.implementation_file_count == 1
    assert result.implementation_sha256 == manifest["implementation_identity"]["sha256"]
    assert (
        result.manifest_sha256
        == hashlib.sha256(result.manifest_path.read_bytes()).hexdigest()
    )
    assert result.strategy_changed is True


def test_a_published_bundle_missing_an_archive_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural check after the rename still sees every archive."""
    config = _config(tmp_path)
    original_publish = backup._publish_bundle

    def lose_one(final: Path, sources: object, manifest: object) -> None:
        original_publish(final, sources, manifest)  # type: ignore[arg-type]
        (final / "files/cohort_ledger.gz").unlink()

    monkeypatch.setattr(backup, "_publish_bundle", lose_one)

    with pytest.raises(CohortPrestartBackupError, match="backup archive is missing"):
        create_cohort_prestart_backup(
            config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
        )


def test_a_level_nine_bundle_still_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bundles written before this change keep verifying unchanged."""
    config = _config(tmp_path)
    monkeypatch.setattr(backup, "_COMPRESS_LEVEL", 9)

    result = create_cohort_prestart_backup(
        config, now=_NOW, implementation_sources=_implementation_sources(tmp_path)
    )

    manifest = verify_cohort_prestart_backup(result.path)
    archive = result.path / manifest["files"][0]["archive_path"]
    assert archive.read_bytes()[8] == 2
