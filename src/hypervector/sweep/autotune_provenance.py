"""Reproduction provenance shared by research and regime tuning boards."""

from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess

import pandas as pd


def bars_window(bars: pd.DataFrame) -> dict[str, object]:
    """First/last bar time and bar count of a loaded frame (UTC ISO strings)."""
    if "timestamp" in bars.columns:
        times = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    elif isinstance(bars.index, pd.DatetimeIndex):
        times = bars.index
    else:
        times = pd.DatetimeIndex([])
    if len(times) == 0:
        return {"first_bar_utc": None, "last_bar_utc": None, "bar_count": len(bars)}
    return {
        "first_bar_utc": _utc_iso(times[0]),
        "last_bar_utc": _utc_iso(times[-1]),
        "bar_count": len(bars),
    }


def _utc_iso(value: pd.Timestamp) -> str:
    stamp = pd.Timestamp(value)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    return stamp.isoformat()


@lru_cache(maxsize=1)
def code_identity() -> dict[str, str | None]:
    """Hash of every ``hypervector`` source file plus the best-effort git commit.

    The tree hash covers sorted relative paths and file bytes, so it changes
    with any uncommitted edit; ``git_commit`` is ``None`` without a checkout.
    """
    import hypervector

    package = Path(hypervector.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {"source_tree_sha256": digest.hexdigest(), "git_commit": _git_commit(package)}


def _git_commit(directory: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    if completed.returncode != 0 or len(commit) != 40:
        return None
    return commit
