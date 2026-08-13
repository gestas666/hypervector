"""Transitive lifecycle-overlap evidence for the exact v39 live run."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

Record = Mapping[str, object]

_SIDES = {"long", "short"}


@dataclass(frozen=True)
class _LifecycleInterval:
    lifecycle_id: str
    route: str
    symbol: str
    side: str
    start_ms: int
    observed_end_ms: int
    status: str
    net_pnl_usd: float


def build_effective_episode_evidence(
    closed_rows: Sequence[Record],
    open_rows: Sequence[Record],
    run_id: str,
) -> dict[str, object]:
    """Group exact-run lifecycles into transitive overlap episodes."""
    exact_run = _text(run_id, "run id")
    closed = [
        _closed_interval(row, exact_run)
        for row in _records(closed_rows, "closed lifecycles")
        if _text(row.get("source_run_id"), "closed source run") == exact_run
    ]
    opened = [
        _open_interval(row, exact_run) for row in _records(open_rows, "open lifecycles")
    ]
    intervals = sorted((*closed, *opened), key=_interval_key)
    _require_unique_lifecycles(intervals)
    clusters = _cluster_intervals(intervals)
    reports = [_cluster_report(index, rows) for index, rows in enumerate(clusters, 1)]
    return {
        "method": "transitive_timestamp_overlap_v1",
        "raw_lifecycles": len(intervals),
        "raw_closed_lifecycles": len(closed),
        "raw_open_lifecycles": len(opened),
        "effective_episode_clusters": len(reports),
        "completed_effective_episodes": sum(
            row["status"] == "completed" for row in reports
        ),
        "ongoing_effective_episodes": sum(
            row["status"] == "ongoing" for row in reports
        ),
        "clusters": reports,
        "independence_established": False,
    }


def _closed_interval(row: Record, run_id: str) -> _LifecycleInterval:
    _require_run(row, run_id, "closed")
    start_ms = _nested_timestamp(row, "entry", "venue_timestamp_ms")
    end_ms = _nested_timestamp(row, "exit", "venue_timestamp_ms")
    if end_ms < start_ms:
        raise ValueError("closed lifecycle exits before its entry")
    return _interval(
        row,
        start_ms=start_ms,
        observed_end_ms=end_ms,
        status="closed",
        net_pnl_usd=_number(row.get("net_pnl_usd"), "closed net PnL"),
    )


def _open_interval(row: Record, run_id: str) -> _LifecycleInterval:
    _require_run(row, run_id, "open")
    start_ms = _nested_timestamp(row, "entry", "venue_timestamp_ms")
    challenger = _mapping(
        row.get("open_profit_lock_challenger"), "open profit-lock challenger"
    )
    observed_ms = _timestamp(challenger.get("as_of_timestamp_ms"), "open as-of")
    if observed_ms < start_ms:
        raise ValueError("open lifecycle observation precedes its entry")
    marked = _mapping(row.get("marked_economics"), "open marked economics")
    return _interval(
        row,
        start_ms=start_ms,
        observed_end_ms=observed_ms,
        status="open",
        net_pnl_usd=_number(
            marked.get("active_lifecycle_marked_net_pnl_usd"), "open marked PnL"
        ),
    )


def _interval(
    row: Record,
    *,
    start_ms: int,
    observed_end_ms: int,
    status: str,
    net_pnl_usd: float,
) -> _LifecycleInterval:
    symbol = _text(row.get("symbol"), "symbol")
    side = _text(row.get("side"), "side")
    if side not in _SIDES:
        raise ValueError("lifecycle side must be long or short")
    strategy = _text(row.get("strategy_id"), "strategy id")
    return _LifecycleInterval(
        lifecycle_id=_text(row.get("lifecycle_id"), "lifecycle id"),
        route=f"{strategy}|{symbol}",
        symbol=symbol,
        side=side,
        start_ms=start_ms,
        observed_end_ms=observed_end_ms,
        status=status,
        net_pnl_usd=net_pnl_usd,
    )


def _cluster_intervals(
    intervals: Sequence[_LifecycleInterval],
) -> list[list[_LifecycleInterval]]:
    clusters: list[list[_LifecycleInterval]] = []
    cluster_end = -1
    for interval in intervals:
        if not clusters or interval.start_ms > cluster_end:
            clusters.append([interval])
            cluster_end = interval.observed_end_ms
            continue
        clusters[-1].append(interval)
        cluster_end = max(cluster_end, interval.observed_end_ms)
    return clusters


def _cluster_report(
    index: int,
    rows: Sequence[_LifecycleInterval],
) -> dict[str, object]:
    ongoing = any(row.status == "open" for row in rows)
    observed_end = max(row.observed_end_ms for row in rows)
    return {
        "episode_id": f"episode_{index:03d}",
        "status": "ongoing" if ongoing else "completed",
        "start_timestamp_ms": min(row.start_ms for row in rows),
        "end_timestamp_ms": None if ongoing else observed_end,
        "observation_end_timestamp_ms": observed_end,
        "lifecycle_count": len(rows),
        "closed_lifecycles": sum(row.status == "closed" for row in rows),
        "open_lifecycles": sum(row.status == "open" for row in rows),
        "closed_net_pnl_usd": sum(
            row.net_pnl_usd for row in rows if row.status == "closed"
        ),
        "open_marked_pnl_usd": sum(
            row.net_pnl_usd for row in rows if row.status == "open"
        ),
        "symbols": sorted({row.symbol for row in rows}),
        "routes": sorted({row.route for row in rows}),
        "sides": sorted({row.side for row in rows}),
        "lifecycle_ids": [row.lifecycle_id for row in rows],
    }


def _nested_timestamp(row: Record, section: str, field: str) -> int:
    nested = _mapping(row.get(section), f"lifecycle {section}")
    return _timestamp(nested.get(field), f"{section} timestamp")


def _require_run(row: Record, run_id: str, label: str) -> None:
    if _text(row.get("source_run_id"), f"{label} source run") != run_id:
        raise ValueError(f"{label} lifecycle source run does not match")


def _require_unique_lifecycles(rows: Sequence[_LifecycleInterval]) -> None:
    identities = [row.lifecycle_id for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("effective episode lifecycle identity is duplicated")


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} must contain objects")
    return list(value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _timestamp(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _interval_key(row: _LifecycleInterval) -> tuple[int, int, str]:
    return row.start_ms, row.observed_end_ms, row.lifecycle_id
