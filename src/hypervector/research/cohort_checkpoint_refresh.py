"""Refresh state and completeness checks for retained cohort checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from hypervector.research.cohort_rolling_checkpoint import is_complete_live_checkpoint


@dataclass
class RefreshFailureMemory:
    """The latest unresolved refresh failure, kept across publication cycles."""

    message: str | None = None


def has_complete_live_checkpoint(path: Path) -> bool:
    """Inspect prior output without accepting malformed or partial evidence."""
    if not path.is_file():
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        return False
    return is_complete_live_checkpoint(document)
