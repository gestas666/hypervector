"""Append-only paper decision ledger.

Phase 3 identity scaffold only: stamps ``execution_mode=paper``, requires a
feed timestamp, writes under ``data/paper/decisions/``, and refuses any path
that resolves under ``data/live/``. No live subscribe / synthetic fill loop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypervector.infra import ensure_data_layout

EXECUTION_MODE = "paper"
DECISIONS_FILENAME = "decisions.jsonl"
FEED_TS_KEY = "feed_ts"
_FEED_TS_ALIASES = (FEED_TS_KEY, "feed_timestamp")


class PaperLedgerError(ValueError):
    """Invalid paper decision record or forbidden write path."""


def _is_under(path: Path, ancestor: Path) -> bool:
    """True if ``path`` is ``ancestor`` or a descendant (after resolve)."""
    p = path.resolve()
    a = ancestor.resolve()
    if p == a:
        return True
    try:
        p.relative_to(a)
        return True
    except ValueError:
        return False


def _has_live_ancestor(path: Path) -> bool:
    """True if any path component is a directory named exactly ``live``."""
    for part in path.resolve().parts:
        if part == "live":
            return True
    return False


def _resolve_feed_ts(record: dict[str, Any]) -> Any:
    for key in _FEED_TS_ALIASES:
        if key in record and record[key] is not None and record[key] != "":
            return record[key]
    raise PaperLedgerError(
        "paper decision record must include a feed timestamp "
        f"({FEED_TS_KEY!r} or 'feed_timestamp')"
    )


def append_paper_decision(data_root: Path | str, record: dict[str, Any]) -> Path:
    """Append one paper decision JSON line under ``data/paper/decisions/``.

    Always stamps ``execution_mode="paper"``. Requires ``feed_ts`` (or
    ``feed_timestamp`` alias, normalized to ``feed_ts``). Creates the I2 layout
    via :func:`ensure_data_layout`. Returns the decisions JSONL path.

    Raises:
        PaperLedgerError: missing feed timestamp, or destination under live/.
    """
    if not isinstance(record, dict):
        raise PaperLedgerError("record must be a dict")

    root = Path(data_root)
    feed_ts = _resolve_feed_ts(record)

    # Refuse before mkdir if the requested root sits under a ``live`` path.
    if _has_live_ancestor(root):
        raise PaperLedgerError(
            f"refusing paper write under live path ({root.resolve()})"
        )

    paths = ensure_data_layout(root)
    dest_dir = paths.paper_decisions
    out_path = dest_dir / DECISIONS_FILENAME

    if _has_live_ancestor(out_path) or _is_under(out_path, paths.live):
        raise PaperLedgerError(
            f"refusing paper write under live path ({out_path.resolve()})"
        )
    if not _is_under(out_path, paths.root / "paper" / "decisions"):
        raise PaperLedgerError(
            f"refusing paper write outside paper/decisions ({out_path})"
        )

    payload = dict(record)
    payload.pop("feed_timestamp", None)
    payload[FEED_TS_KEY] = feed_ts
    payload["execution_mode"] = EXECUTION_MODE

    dest_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str, separators=(",", ":"))
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return out_path
