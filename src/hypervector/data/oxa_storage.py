"""Atomic immutable storage helpers for 0xArchive evidence bundles."""

from __future__ import annotations

import hashlib
import gzip
import io
import json
import logging
import shutil
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, TextIO

logger = logging.getLogger(__name__)


def publish_immutable_directory(
    final: Path,
    writer: Callable[[Path], None],
) -> None:
    """Publish a staged directory once, cleaning only its private staging path."""
    if final.exists():
        raise FileExistsError(f"0xArchive output already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=final.parent))
    published = False
    try:
        writer(staging)
        staging.rename(final)
        published = True
    finally:
        if not published:
            try:
                shutil.rmtree(staging)
            except OSError as exc:
                logger.warning(
                    "oxa_staging_cleanup_failed path=%s error=%s",
                    staging,
                    type(exc).__name__,
                )


def write_json(path: Path, payload: object) -> None:
    """Write deterministic formatted JSON to a new bundle file."""
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")


@contextmanager
def gzip_text_writer(path: Path) -> Iterator[TextIO]:
    """Open a new deterministic gzip text stream for atomic bundle staging."""
    with path.open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8") as handle:
                yield handle


def open_text_reader(path: Path) -> IO[str]:
    """Open UTF-8 text from an uncompressed or gzip-compressed evidence file."""
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def write_gzip_json(path: Path, payload: object) -> None:
    """Write deterministic formatted JSON to a new gzip bundle file."""
    with gzip_text_writer(path) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def file_evidence(path: Path) -> dict[str, object]:
    """Return byte length and SHA-256 for one completed evidence file."""
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return {"sha256": digest.hexdigest(), "bytes": byte_count}


def verify_file_evidence(bundle: Path, value: object) -> None:
    """Verify every safe relative file declared by an immutable manifest."""
    if not isinstance(value, dict) or not value:
        raise ValueError(f"bundle manifest has no file evidence: {bundle}")
    for relative, expected in value.items():
        _verify_one_file(bundle, relative, expected)


def _verify_one_file(bundle: Path, relative: object, expected: object) -> None:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"bundle manifest has an invalid file path: {bundle}")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"bundle manifest file path is unsafe: {relative!r}")
    if not isinstance(expected, dict):
        raise ValueError(f"bundle manifest has invalid file evidence: {relative}")
    path = bundle / candidate
    if not path.is_file():
        raise ValueError(f"bundle evidence file is missing: {path}")
    observed = file_evidence(path)
    if observed.get("bytes") != expected.get("bytes"):
        raise ValueError(f"bundle evidence byte count mismatch: {path}")
    if observed.get("sha256") != expected.get("sha256"):
        raise ValueError(f"bundle evidence checksum mismatch: {path}")
