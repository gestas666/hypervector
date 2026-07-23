"""Read-only live decision ledger summary (ops).

Pure counters over ``data/live/decisions/decisions.jsonl``. Never places
orders. Used by ``live-report`` CLI. Symmetric to :mod:`hypervector.paper.report`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.live.ledger import DECISIONS_FILENAME
from hypervector.paper.report import load_decision_rows

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


def default_live_decisions_path(data_root: Path | str) -> Path:
    return paths_for(data_root).live_decisions / DECISIONS_FILENAME


def _count(values: list[Any]) -> dict[str, int]:
    c = Counter("" if v is None else str(v) for v in values)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


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


def summarize_live_decisions(
    rows: list[dict[str, Any]],
    *,
    decisions_path: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Aggregate honesty + ops counters for live ledgers."""
    n = max(0, int(last_n))
    market_fills = [
        r
        for r in rows
        if r.get("action") != "funding"
        and (
            str(r.get("action") or "") in _MARKET_ACTIONS
            or r.get("fill_model_id") is not None
            or r.get("place_attempted") is True
        )
    ]
    funding = [r for r in rows if r.get("action") == "funding"]
    session_starts = [r for r in rows if r.get("action") == "session_start"]

    sample = []
    for r in market_fills[-n:]:
        oi = r.get("order_intent") if isinstance(r.get("order_intent"), dict) else {}
        sample.append(
            {
                "feed_ts": r.get("feed_ts"),
                "action": r.get("action"),
                "execution_mode": r.get("execution_mode"),
                "submitted": r.get("submitted"),
                "place_attempted": r.get("place_attempted"),
                "live_phase": r.get("live_phase"),
                "venue_order_id": r.get("venue_order_id"),
                "submit_error": r.get("submit_error"),
                "network": r.get("network"),
                "fill_model_id": r.get("fill_model_id"),
                "order_intent_submit_enabled": oi.get("submit_enabled") if oi else None,
            }
        )

    submitted_true = sum(1 for r in rows if r.get("submitted") is True)
    place_true = sum(1 for r in rows if r.get("place_attempted") is True)
    live_phase_true = sum(1 for r in rows if r.get("live_phase") is True)

    return {
        "ok": True,
        "ledger": "live",
        "decisions_path": str(decisions_path) if decisions_path is not None else None,
        "rows": len(rows),
        "market_fills": len(market_fills),
        "funding_rows": len(funding),
        "session_start_rows": len(session_starts),
        "execution_mode": _count([r.get("execution_mode") for r in rows]),
        "submitted": _count([r.get("submitted") for r in rows]),
        "place_attempted": _count([r.get("place_attempted") for r in rows]),
        "live_phase": _count([r.get("live_phase") for r in rows]),
        "network": _count([r.get("network") for r in rows]),
        "action": _count([r.get("action") for r in market_fills]),
        "fill_model_id": _count([r.get("fill_model_id") for r in market_fills]),
        "submit_error": _count(
            [r.get("submit_error") for r in market_fills if r.get("submit_error")]
        ),
        "honesty": {
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
            "all_execution_mode_live": all(
                str(r.get("execution_mode")) == "live"
                for r in rows
                if r.get("execution_mode") is not None
            )
            if rows
            else True,
            "submitted_true_count": submitted_true,
            "place_attempted_true_count": place_true,
            "live_phase_true_count": live_phase_true,
        },
        "last_market": sample,
        "live_submit_implemented": True,
        "command": "live-run",
    }


def report_from_data_root(
    data_root: Path | str,
    *,
    decisions_path: Path | str | None = None,
    last_n: int = 5,
) -> dict[str, Any]:
    """Load live decisions path and summarize. Refuses paper/ paths."""
    root = Path(data_root)
    path = (
        Path(decisions_path)
        if decisions_path is not None
        else default_live_decisions_path(root)
    )
    paths = paths_for(root)
    paper_root = paths.paper_decisions.parent  # .../paper
    if _is_under(path, paper_root):
        raise ValueError(f"refusing live-report on path under paper/: {path}")
    parts = path.resolve().parts
    if "paper" in parts and "live" not in parts:
        raise ValueError(f"refusing live-report on paper path: {path}")

    rows = load_decision_rows(path)
    return summarize_live_decisions(rows, decisions_path=path, last_n=last_n)
