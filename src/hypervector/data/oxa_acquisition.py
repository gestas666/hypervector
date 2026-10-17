"""Fail-early, never-partial publication rules for bounded 0xArchive fetches.

Every single-window fetcher follows the same order:

1. Before any vendor call, inspect the deterministic canonical directory. A
   complete bundle with the same identity is verified and reused; anything else
   there fails immediately, so a retry never spends API calls just to discover
   that the output path is taken.
2. After fetching, an unfinished cursor chain is never published at the
   canonical path. By default nothing is stored; an explicit ``allow_partial``
   publishes to a ``_partial`` sibling that backfill, audit and the research
   database never read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from hypervector.data.oxa_storage import verify_file_evidence

PARTIAL_SUFFIX = "_partial"


def partial_directory(directory: Path) -> Path:
    """Return the non-canonical sibling used only for explicit partial fetches."""
    return directory.with_name(directory.name + PARTIAL_SUFFIX)


def reusable_bundle_manifest(
    directory: Path,
    *,
    kind: str,
    expected: Mapping[str, object],
    verify_files: bool = True,
) -> dict[str, object] | None:
    """Return a verified complete manifest at ``directory`` or ``None`` if absent.

    Raises ``ValueError`` without touching the directory when it holds an
    incomplete, foreign, unreadable, or corrupted bundle. ``verify_files=False``
    is only for callers that run a stronger reader-side verification next.
    """
    if not directory.exists():
        return None
    manifest = _read_manifest(directory, kind)
    if manifest.get("complete") is not True:
        raise ValueError(
            f"existing {kind} bundle is incomplete "
            f"(max_pages={manifest.get('max_pages')!r}, "
            f"continuation_cursor={manifest.get('continuation_cursor')!r}): "
            f"{directory}; move it aside before refetching"
        )
    mismatched = sorted(
        key for key, value in expected.items() if manifest.get(key) != value
    )
    if mismatched:
        raise ValueError(
            f"existing {kind} bundle identity differs from the request "
            f"({', '.join(mismatched)}): {directory}"
        )
    if verify_files:
        verify_file_evidence(directory, manifest.get("files"))
    return manifest


def bundle_report(
    directory: Path,
    *,
    identity: Mapping[str, object],
    path_key: str,
    normalized_names: tuple[str, ...],
    counts: tuple[str, ...],
    reused: bool,
    partial: bool = False,
) -> dict[str, object]:
    """Build one secret-free acquisition report from a published manifest."""
    manifest = _read_manifest(directory, "published")
    files = manifest.get("files")
    names = files if isinstance(files, dict) else {}
    normalized = next(
        (name for name in normalized_names if name in names), normalized_names[0]
    )
    report: dict[str, object] = {"ok": True, **identity}
    report["directory"] = str(directory.resolve())
    report[path_key] = str((directory / normalized).resolve())
    report["manifest_path"] = str((directory / "manifest.json").resolve())
    for key in counts:
        report[key] = manifest.get(key)
    report["complete"] = manifest.get("complete")
    report["continuation_cursor"] = manifest.get("continuation_cursor")
    report["reused"] = reused
    if partial:
        report["partial"] = True
    return report


def reject_existing_partial(directory: Path, *, kind: str) -> None:
    """Fail before vendor calls when an explicit partial output is taken."""
    partial = partial_directory(directory)
    if partial.exists():
        raise ValueError(
            f"partial {kind} bundle already exists: {partial}; "
            "move it aside before fetching another partial window"
        )


def incomplete_fetch_error(
    kind: str,
    *,
    page_count: int,
    continuation_cursor: str | None,
    hint: str = "rerun with a larger --max-pages",
    window: str | None = None,
) -> ValueError:
    """Return the actionable error for an exhausted page budget."""
    subject = f" for {window}" if window else ""
    return ValueError(
        f"{kind} max-pages exhausted{subject} before completing the window after "
        f"{page_count} page(s) (continuation_cursor={continuation_cursor!r}); "
        f"nothing was stored; {hint}"
    )


def _read_manifest(directory: Path, kind: str) -> dict[str, object]:
    path = directory / "manifest.json"
    if not path.is_file():
        raise ValueError(
            f"existing {kind} output has no manifest: {directory}; "
            "move it aside before refetching"
        )
    try:
        manifest: object = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"existing {kind} manifest is unreadable: {path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"existing {kind} manifest must be an object: {path}")
    return manifest
