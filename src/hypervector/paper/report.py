"""Read-only paper decision ledger summary (dry-run ops).

Pure counters over ``decisions.jsonl``. Never submits orders, never writes
under ``data/live/``. Used by ``paper-report`` CLI.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.paper.ledger import DECISIONS_FILENAME

# Market-like actions that may carry fills / order_intent (not funding).
_MARKET_ACTIONS = frozenset(
    {
        "enter_long",
        "enter_short",
        "close",
        "close_long",
        "close_short",
        "exit",
        "flatten",
    }
)


def default_decisions_path(data_root: Path | str) -> Path:
    """I2 paper decisions JSONL path for ``data_root``."""
    return paths_for(data_root).paper_decisions / DECISIONS_FILENAME


def load_decision_rows(path: Path | str) -> list[dict[str, Any]]:
    """Load JSONL decision records; skip blank lines. Raises on invalid JSON."""
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {p}:{line_no}: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"decision row must be object at {p}:{line_no}")
            rows.append(obj)
    return rows


def _count(values: list[Any]) -> dict[str, int]:
    c = Counter("" if v is None else str(v) for v in values)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def summarize_paper_decisions(
    rows: list[dict[str, Any]],
    *,
    decisions_path: Path | str | None = None,
    data_root: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Aggregate honesty + ops counters for paper/shadow dry-run ledgers.

    Parameters
    ----------
    rows:
        Decision dicts (typically from :func:`load_decision_rows`).
    decisions_path:
        Optional path echoed in the report.
    data_root:
        If set, count files under ``live/`` (must be zero for paper-complete).
    last_n:
        How many recent market rows to sample (not funding).
    """
    n = max(0, int(last_n))
    # Prefer explicit market actions; if fill_model without action, keep those too.
    market_fills = [
        r
        for r in rows
        if r.get("action") != "funding" and r.get("fill_model_id") is not None
    ]
    funding = [r for r in rows if r.get("action") == "funding"]
    intents = [
        r.get("order_intent")
        for r in market_fills
        if isinstance(r.get("order_intent"), dict)
    ]

    live_files = 0
    if data_root is not None:
        live_root = paths_for(data_root).live
        if live_root.is_dir():
            live_files = sum(1 for p in live_root.rglob("*") if p.is_file())

    submitted_true = sum(1 for r in rows if r.get("submitted") is True)
    intent_submit_true = sum(
        1 for oi in intents if isinstance(oi, dict) and oi.get("submit_enabled") is True
    )

    sample = []
    for r in market_fills[-n:]:
        oi = r.get("order_intent") if isinstance(r.get("order_intent"), dict) else {}
        sample.append(
            {
                "feed_ts": r.get("feed_ts"),
                "action": r.get("action"),
                "execution_mode": r.get("execution_mode"),
                "submitted": r.get("submitted"),
                "network": r.get("network"),
                "fill_model_id": r.get("fill_model_id"),
                "fill_fallback_reason": r.get("fill_fallback_reason"),
                "order_intent_schema": oi.get("schema") if oi else None,
                "order_intent_submit_enabled": oi.get("submit_enabled") if oi else None,
            }
        )

    honesty = {
        "all_submitted_false_or_absent": submitted_true == 0,
        "all_intent_submit_enabled_false": intent_submit_true == 0,
        "live_files": live_files,
        "no_live_files": live_files == 0,
        "modes_seen": sorted(
            {
                str(r.get("execution_mode"))
                for r in rows
                if r.get("execution_mode") is not None
            }
        ),
        "networks_seen": sorted(
            {str(r.get("network")) for r in rows if r.get("network") is not None}
        ),
    }

    return {
        "ok": True,
        "decisions_path": str(decisions_path) if decisions_path is not None else None,
        "rows": len(rows),
        "market_fills": len(market_fills),
        "funding_rows": len(funding),
        "execution_mode": _count([r.get("execution_mode") for r in rows]),
        "submitted": _count([r.get("submitted") for r in rows]),
        "network": _count([r.get("network") for r in rows]),
        "action": _count([r.get("action") for r in market_fills]),
        "fill_model_id": _count([r.get("fill_model_id") for r in market_fills]),
        "fill_fallback_reason": _count(
            [r.get("fill_fallback_reason") for r in market_fills]
        ),
        "order_intent": {
            "count": len(intents),
            "missing_on_market_fills": max(0, len(market_fills) - len(intents)),
            "schema": _count(
                [oi.get("schema") for oi in intents if isinstance(oi, dict)]
            ),
            "submit_enabled": _count(
                [oi.get("submit_enabled") for oi in intents if isinstance(oi, dict)]
            ),
        },
        "honesty": honesty,
        "last_market": sample,
        "no_submit": True,  # this ledger path never submits
        # Product-wide: venue submit exists via live-run (not this paper report).
        "live_submit_implemented": True,
        "live_submit_command": "live-run",
    }


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


def report_from_data_root(
    data_root: Path | str,
    *,
    decisions_path: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Load default (or override) decisions path and summarize."""
    root = Path(data_root)
    path = (
        Path(decisions_path)
        if decisions_path is not None
        else default_decisions_path(root)
    )
    live_root = paths_for(root).live
    if _is_under(path, live_root):
        raise ValueError(f"refusing paper-report on path under live/: {path}")
    # Reject absolute live paths even when data_root differs.
    if "live" in path.resolve().parts and "paper" not in path.resolve().parts:
        raise ValueError(f"refusing paper-report on live path: {path}")

    rows = load_decision_rows(path)
    return summarize_paper_decisions(
        rows,
        decisions_path=path,
        data_root=root,
        last_n=last_n,
    )
