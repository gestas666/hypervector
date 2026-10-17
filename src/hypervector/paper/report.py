"""Read-only paper decision ledger summary (dry-run ops).

Pure counters over ``decisions.jsonl``. Never submits orders, never writes
under ``data/live/``. Used by ``paper-report`` CLI.
"""

from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import dataclass, field
from collections.abc import Iterable
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
    with p.open(encoding="utf-8") as fh:
        return load_decision_stream(fh, source_label=str(p))


def iter_decision_stream(
    lines: Iterable[str], *, source_label: str
) -> Iterable[dict[str, object]]:
    """Yield strict JSONL records from a caller-owned immutable stream."""
    for line_no, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid JSONL at {source_label}:{line_no}: {exc}"
            ) from exc
        if not isinstance(obj, dict):
            raise ValueError(f"decision row must be object at {source_label}:{line_no}")
        yield obj


def _count(values: list[Any]) -> dict[str, int]:
    c = Counter("" if v is None else str(v) for v in values)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def summarize_paper_decisions(
    rows: Iterable[dict[str, object]],
    *, decisions_path: Path | str | None = None,
    data_root: Path | str | None = None, last_n: int = 5,
) -> dict[str, object]:
    """Summarize a single-pass ledger using counters and a bounded recent sample."""
    state = _PaperSummary(last_n=max(0, int(last_n)))
    for row in rows:
        state.add(row)
    live_files = 0
    if data_root is not None:
        live_root = paths_for(data_root).live
        if live_root.is_dir():
            live_files = sum(1 for path in live_root.rglob("*") if path.is_file())
    return state.report(decisions_path, live_files)



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

    rows = iter_decision_rows(path)
    return summarize_paper_decisions(
        rows,
        decisions_path=path,
        data_root=root,
        last_n=last_n,
    )


def load_decision_stream(lines: Iterable[str], *, source_label: str) -> list[dict[str, object]]:
    """Retain the materialized API for callers requiring immutable replay rows."""
    return list(iter_decision_stream(lines, source_label=source_label))


def iter_decision_rows(path: Path | str) -> Iterable[dict[str, object]]:
    """Stream a ledger while owning its file for the duration of iteration."""
    source = Path(path)
    if not source.is_file():
        return
    with source.open(encoding="utf-8") as stream:
        yield from iter_decision_stream(stream, source_label=str(source))


@dataclass
class _PaperSummary:
    last_n: int
    rows: int = 0
    markets: int = 0
    funding: int = 0
    intents: int = 0
    submitted: int = 0
    intent_submit: int = 0
    counts: dict[str, Counter[str]] = field(default_factory=dict)
    modes: set[str] = field(default_factory=set)
    networks: set[str] = field(default_factory=set)
    recent: deque[dict[str, object]] = field(init=False)

    def __post_init__(self) -> None:
        self.recent = deque(maxlen=self.last_n)

    def count(self, field_name: str, value: object) -> None:
        self.counts.setdefault(field_name, Counter())["" if value is None else str(value)] += 1

    def add(self, row: dict[str, object]) -> None:
        self.rows += 1
        self.funding += row.get("action") == "funding"
        self.submitted += row.get("submitted") is True
        for name in ("execution_mode", "submitted", "network"):
            self.count(name, row.get(name))
        if row.get("execution_mode") is not None:
            self.modes.add(str(row["execution_mode"]))
        if row.get("network") is not None:
            self.networks.add(str(row["network"]))
        if row.get("action") == "funding" or row.get("fill_model_id") is None:
            return
        self.markets += 1
        for name in ("action", "fill_model_id", "fill_fallback_reason"):
            self.count(name, row.get(name))
        intent = row.get("order_intent")
        if isinstance(intent, dict):
            self.intents += 1
            self.intent_submit += intent.get("submit_enabled") is True
            self.count("intent_schema", intent.get("schema"))
            self.count("intent_submit_enabled", intent.get("submit_enabled"))
        self.recent.append(_paper_sample(row))

    def totals(self, name: str) -> dict[str, int]:
        return dict(sorted(self.counts.get(name, {}).items(), key=lambda item: (-item[1], item[0])))

    def report(self, path: Path | str | None, live_files: int) -> dict[str, object]:
        report: dict[str, object] = {
            "ok": True, "decisions_path": str(path) if path is not None else None,
            "rows": self.rows, "market_fills": self.markets, "funding_rows": self.funding,
            "order_intent": {"count": self.intents,
                "missing_on_market_fills": self.markets - self.intents,
                "schema": self.totals("intent_schema"),
                "submit_enabled": self.totals("intent_submit_enabled")},
            "honesty": {"all_submitted_false_or_absent": self.submitted == 0,
                "all_intent_submit_enabled_false": self.intent_submit == 0,
                "live_files": live_files, "no_live_files": live_files == 0,
                "modes_seen": sorted(self.modes), "networks_seen": sorted(self.networks)},
            "last_market": list(self.recent), "no_submit": True,
            "live_submit_implemented": True, "live_submit_command": "live-run",
        }
        for name in ("execution_mode", "submitted", "network", "action", "fill_model_id", "fill_fallback_reason"):
            report[name] = self.totals(name)
        return report


def _paper_sample(row: dict[str, object]) -> dict[str, object]:
    intent = row.get("order_intent")
    sample = {name: row.get(name) for name in (
        "feed_ts", "action", "execution_mode", "submitted", "network",
        "fill_model_id", "fill_fallback_reason")}
    sample["order_intent_schema"] = intent.get("schema") if isinstance(intent, dict) else None
    sample["order_intent_submit_enabled"] = intent.get("submit_enabled") if isinstance(intent, dict) else None
    return sample
