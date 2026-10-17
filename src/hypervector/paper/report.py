"""Read-only paper decision ledger summary (dry-run ops).

Pure counters over ``decisions.jsonl``. Never submits orders, never writes
under ``data/live/``. Used by ``paper-report`` CLI.

Only real fills feed ``market_fills`` and the fill-model attribution: order
lifecycle rows (``order_status``), zero-quantity skipped fills and funding are
counted separately. The honesty block's ``live_files`` counts paper/shadow
artifacts found under ``live/`` (a misrouted paper write), not the files a
co-hosted live runtime owns there, and it never walks the whole live tree.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.paper.ledger import ALLOWED_EXECUTION_MODES, DECISIONS_FILENAME

logger = logging.getLogger(__name__)

LIVE_FILES_SCOPE = "paper_artifacts_under_live"
# Live directories a misrouted paper ledger could reach; scanned one level deep.
_LIVE_LEDGER_DIRS = ("decisions", "ledger")


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
    lines: Iterable[str],
    *,
    source_label: str,
    on_torn_tail: Callable[[int], None] | None = None,
) -> Iterable[dict[str, object]]:
    """Yield strict JSONL records from a caller-owned immutable stream.

    With ``on_torn_tail`` (file-backed streams only), an unparseable final
    line that lacks its newline is reported and skipped instead of raising;
    every interior line stays strict.
    """
    for line_no, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            if on_torn_tail is not None and not line.endswith("\n"):
                on_torn_tail(line_no)
                continue
            raise ValueError(
                f"invalid JSONL at {source_label}:{line_no}: {exc}"
            ) from exc
        if not isinstance(obj, dict):
            raise ValueError(f"decision row must be object at {source_label}:{line_no}")
        yield obj


def _count(values: list[Any]) -> dict[str, int]:
    c = Counter("" if v is None else str(v) for v in values)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def is_market_fill(row: dict[str, object]) -> bool:
    """Return whether a ledger row records a real (non-zero) fill.

    Uses no action allow-list so liquidations, target reductions and future
    fill actions still count. Rows without any quantity field are legacy fills.
    """
    if row.get("action") == "funding" or row.get("fill_model_id") is None:
        return False
    if row.get("skipped") is True or "order_status" in row:
        return False
    quantity = row.get("fill_qty", row.get("qty"))
    if quantity is None:
        return True
    try:
        return float(quantity) > 0.0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def summarize_paper_decisions(
    rows: Iterable[dict[str, object]],
    *,
    decisions_path: Path | str | None = None,
    data_root: Path | str | None = None,
    last_n: int = 5,
    run_id: str | None = None,
    strategy: str | None = None,
) -> dict[str, object]:
    """Summarize a single-pass ledger using counters and a bounded recent sample."""
    state = _PaperSummary(last_n=max(0, int(last_n)))
    for row in rows:
        if run_id is not None and row.get("run_id") != run_id:
            continue
        if strategy is not None and row.get("strategy_name") != strategy:
            continue
        state.add(row)
    live_files = paper_artifacts_under_live(data_root) if data_root is not None else 0
    report = state.report(decisions_path, live_files)
    report["filters"] = {"run_id": run_id, "strategy": strategy}
    return report


def paper_artifacts_under_live(data_root: Path | str) -> int:
    """Count paper/shadow-stamped artifacts under ``live/`` without a tree walk.

    Checks the two places a misrouted paper write could land: a paper layout
    nested under ``live/paper/`` (every file there counts), and JSONL files
    directly in ``live/decisions`` or ``live/ledger`` whose first record is
    stamped ``paper`` or ``shadow``. Files a live runtime writes are ignored.
    """
    live_root = paths_for(data_root).live
    if not live_root.is_dir():
        return 0
    count = 0
    nested = live_root / "paper"
    if nested.is_dir():
        count += sum(1 for path in nested.rglob("*") if path.is_file())
    for name in _LIVE_LEDGER_DIRS:
        directory = live_root / name
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            if path.is_file() and _first_record_mode(path) in ALLOWED_EXECUTION_MODES:
                count += 1
    return count


def _first_record_mode(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    return row.get("execution_mode") if isinstance(row, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return None


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
    run_id: str | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Load default (or override) decisions path and summarize.

    ``run_id`` and ``strategy`` optionally restrict the summary to one run or
    one strategy when a ledger mixes several profiles' runs.
    """
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

    torn: list[int] = []
    rows = iter_decision_rows(path, on_torn_tail=torn.append)
    report = summarize_paper_decisions(
        rows,
        decisions_path=path,
        data_root=root,
        last_n=last_n,
        run_id=run_id,
        strategy=strategy,
    )
    if torn:
        logger.warning("paper report skipped torn final ledger line %s", torn[-1])
    report["torn_tail_skipped"] = bool(torn)
    return report


def load_decision_stream(lines: Iterable[str], *, source_label: str) -> list[dict[str, object]]:
    """Retain the materialized API for callers requiring immutable replay rows."""
    return list(iter_decision_stream(lines, source_label=source_label))


def iter_decision_rows(
    path: Path | str,
    *,
    on_torn_tail: Callable[[int], None] | None = None,
) -> Iterable[dict[str, object]]:
    """Stream a ledger while owning its file for the duration of iteration."""
    source = Path(path)
    if not source.is_file():
        return
    with source.open(encoding="utf-8") as stream:
        yield from iter_decision_stream(
            stream, source_label=str(source), on_torn_tail=on_torn_tail
        )


@dataclass
class _PaperSummary:
    last_n: int
    rows: int = 0
    markets: int = 0
    funding: int = 0
    intents: int = 0
    submitted: int = 0
    intent_submit: int = 0
    order_events: int = 0
    skipped_fills: int = 0
    counts: dict[str, Counter[str]] = field(default_factory=dict)
    modes: set[str] = field(default_factory=set)
    networks: set[str] = field(default_factory=set)
    recent: deque[dict[str, object]] = field(init=False)

    def __post_init__(self) -> None:
        self.recent = deque(maxlen=self.last_n)

    def count(self, field_name: str, value: object) -> None:
        # get-then-create: setdefault(name, Counter()) built a Counter per row.
        counter = self.counts.get(field_name)
        if counter is None:
            counter = self.counts[field_name] = Counter()
        counter["" if value is None else str(value)] += 1

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
        intent = row.get("order_intent")
        if isinstance(intent, dict):
            # Any submit-enabled intent breaks honesty, fill or not.
            self.intent_submit += intent.get("submit_enabled") is True
        if "order_status" in row:
            self.order_events += 1
            self.count("order_event_action", row.get("action"))
            return
        if row.get("skipped") is True:
            self.skipped_fills += 1
            return
        if not is_market_fill(row):
            return
        self.markets += 1
        for name in ("action", "fill_model_id", "fill_fallback_reason"):
            self.count(name, row.get(name))
        if isinstance(intent, dict):
            self.intents += 1
            self.count("intent_schema", intent.get("schema"))
            self.count("intent_submit_enabled", intent.get("submit_enabled"))
        self.recent.append(_paper_sample(row))

    def totals(self, name: str) -> dict[str, int]:
        return dict(sorted(self.counts.get(name, {}).items(), key=lambda item: (-item[1], item[0])))

    def report(self, path: Path | str | None, live_files: int) -> dict[str, object]:
        report: dict[str, object] = {
            "ok": True, "decisions_path": str(path) if path is not None else None,
            "rows": self.rows, "market_fills": self.markets, "funding_rows": self.funding,
            "order_events": {"count": self.order_events,
                "action": self.totals("order_event_action")},
            "skipped_fills": self.skipped_fills,
            "order_intent": {"count": self.intents,
                "missing_on_market_fills": self.markets - self.intents,
                "schema": self.totals("intent_schema"),
                "submit_enabled": self.totals("intent_submit_enabled")},
            "honesty": {"all_submitted_false_or_absent": self.submitted == 0,
                "all_intent_submit_enabled_false": self.intent_submit == 0,
                "live_files": live_files, "no_live_files": live_files == 0,
                "live_files_scope": LIVE_FILES_SCOPE,
                "modes_seen": sorted(self.modes), "networks_seen": sorted(self.networks)},
            "last_market": list(self.recent), "no_submit": True,
            "live_submit_implemented": True, "live_submit_command": "live start",
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
