"""Append-only **live** decision ledger under ``data/live/decisions/``.

Separate from paper: never writes under ``data/paper/``. Foundation for
Phase 4b-live (venue submit wired later).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hypervector.infra import ensure_data_layout

EXECUTION_MODE_LIVE = "live"
ALLOWED_LIVE_EXECUTION_MODES = frozenset({"live"})
DECISIONS_FILENAME = "decisions.jsonl"
FEED_TS_KEY = "feed_ts"
_FEED_TS_ALIASES = (FEED_TS_KEY, "feed_timestamp")


class LiveLedgerError(ValueError):
    """Invalid live decision record or forbidden write path."""


def _is_under(path: Path, ancestor: Path) -> bool:
    p = path.resolve()
    a = ancestor.resolve()
    if p == a:
        return True
    try:
        p.relative_to(a)
        return True
    except ValueError:
        return False


def _has_paper_ancestor(path: Path) -> bool:
    for part in path.resolve().parts:
        if part == "paper":
            return True
    return False


def _resolve_feed_ts(record: dict[str, Any]) -> Any:
    for key in _FEED_TS_ALIASES:
        if key in record and record[key] is not None and record[key] != "":
            return record[key]
    raise LiveLedgerError(
        "live decision record must include a feed timestamp "
        f"({FEED_TS_KEY!r} or 'feed_timestamp')"
    )


def append_live_decision(data_root: Path | str, record: dict[str, Any]) -> Path:
    """Append one live decision JSON line under ``data/live/decisions/``.

    Stamps ``execution_mode=live``. Requires ``feed_ts``. Refuses any
    destination under ``paper/``.

    Returns the live decisions JSONL path.
    """
    if not isinstance(record, dict):
        raise LiveLedgerError("record must be a dict")

    root = Path(data_root)
    feed_ts = _resolve_feed_ts(record)

    if _has_paper_ancestor(root):
        raise LiveLedgerError(
            f"refusing live write under paper path ({root.resolve()})"
        )

    paths = ensure_data_layout(root)
    dest_dir = paths.live_decisions
    out_path = dest_dir / DECISIONS_FILENAME

    if _has_paper_ancestor(out_path) or _is_under(out_path, paths.paper_decisions):
        raise LiveLedgerError(
            f"refusing live write under paper path ({out_path.resolve()})"
        )
    if not _is_under(out_path, paths.root / "live" / "decisions"):
        raise LiveLedgerError(
            f"refusing live write outside live/decisions ({out_path})"
        )

    payload = dict(record)
    payload.pop("feed_timestamp", None)
    payload[FEED_TS_KEY] = feed_ts
    # Live mode is structural for this ledger — always stamp live.
    payload["execution_mode"] = EXECUTION_MODE_LIVE
    payload.setdefault("network", "mainnet")

    dest_dir.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str, separators=(",", ":"))
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return out_path
