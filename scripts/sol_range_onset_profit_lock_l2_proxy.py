#!/usr/bin/env python3
"""Publish immutable SOL Range Onset profit-lock L2 proxy evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import sys

import duckdb

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_profit_lock_l2_proxy import (
    ProxyLifecycle,
    ProxyMinuteBar,
    build_profit_lock_proxy_report,
)
from hypervector.research.sol_range_onset_target_exit_audit import (
    audit_target_exit_blocks,
)

_SYMBOL = "SOL"
_SURFACE = "v49-target-exit-posthoc"
_THRESHOLDS_MS = (5_000, 10_000, 15_000, 30_000, 60_000)
_MINUTE_MS = 60_000
_POLICIES = (
    "a25_floor15_trail10",
    "a40_floor15_trail20",
    "a60_floor15_trail30",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only SOL profit-lock proxy parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-trades", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> int:
    """Validate exact inputs and publish one authority-free proxy report."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    paths = tuple(Path(path) for path in args.artifact)
    evidence_before = tuple(file_evidence(path) for path in paths)
    audit = audit_target_exit_blocks(paths, expected_trades=args.expected_trades)
    database = Path(args.database).resolve()
    _require_database_identity(paths, database)
    database_before = _database_file_identity(database)
    lifecycles = _load_lifecycles(audit)
    start_ms, end_ms = _bounds(lifecycles)
    bars = _load_bars(database, start_ms, end_ms)
    report = build_profit_lock_proxy_report(lifecycles, bars, _THRESHOLDS_MS)
    report.update(
        {
            "selection": _selection(lifecycles, audit),
            "assessment": _assessment(report),
            "sources": _sources(
                paths, evidence_before, database, database_before, bars
            ),
            "limitations": [*_limitations(), *report["limitations"]],
        }
    )
    _require_unchanged(paths, evidence_before, database, database_before)
    write_immutable_json(output, report)
    return 0


def _load_lifecycles(audit: Mapping[str, object]) -> tuple[ProxyLifecycle, ...]:
    sources = _sequence(audit.get("source_evidence"), "source evidence")
    values: list[ProxyLifecycle] = []
    for index, source in enumerate(sources, 1):
        path = Path(str(_mapping(source, "source").get("path")))
        payload = _read_mapping(path)
        replay = _native_replay(payload, path)
        phase = f"block_{index:02d}"
        values.extend(_proxy_trade(row, phase) for row in _trades(replay, path))
    identities = [value.lifecycle_id for value in values]
    if len(identities) != len(set(identities)):
        raise ValueError("SOL profit-lock lifecycle identities are not unique")
    return tuple(values)


def _native_replay(payload: Mapping[str, object], path: Path) -> Mapping[str, object]:
    continuous = _mapping(payload.get("continuous"), "continuous")
    trials = _sequence(continuous.get("trials"), "trials")
    selected = []
    for value in trials:
        row = _mapping(value, "trial row")
        config = _mapping(row.get("trial"), "trial config")
        if config.get("target_bps") is None:
            selected.append(_mapping(row.get("event_replay"), "event replay"))
    if len(selected) != 1 or selected[0].get("status") != "complete":
        raise ValueError(f"SOL native replay is missing or incomplete: {path}")
    return selected[0]


def _trades(
    replay: Mapping[str, object], path: Path
) -> tuple[Mapping[str, object], ...]:
    values = tuple(
        _mapping(value, "trade") for value in _sequence(replay.get("trades"), "trades")
    )
    declared = _integer(replay.get("completed_trades"), "completed trades")
    if declared != len(values):
        raise ValueError(f"SOL native replay trade count differs: {path}")
    return values


def _proxy_trade(row: Mapping[str, object], phase: str) -> ProxyLifecycle:
    entry_ms = _integer(row.get("entry_snapshot_time_ms"), "entry timestamp")
    return ProxyLifecycle(
        lifecycle_id=f"SOL:{phase}:{entry_ms}",
        phase=phase,
        side=_side(row.get("direction")),
        entry_timestamp_ms=entry_ms,
        exit_timestamp_ms=_integer(row.get("exit_snapshot_time_ms"), "exit timestamp"),
        entry_price=_number(row.get("entry_price"), "entry price"),
        exit_price=_number(row.get("exit_price"), "exit price"),
        quantity=_number(row.get("quantity"), "quantity"),
        gross_pnl_usd=_number(row.get("gross_pnl_usd"), "gross PnL"),
        fees_usd=_number(row.get("fees_usd"), "fees"),
    )


def _require_database_identity(paths: Sequence[Path], database: Path) -> None:
    declared: set[Path] = set()
    for path in paths:
        payload = _read_mapping(path)
        coverage = _mapping(payload.get("database_coverage"), "database coverage")
        raw = coverage.get("database_path")
        if not isinstance(raw, str) or not raw:
            raise ValueError(f"SOL target artifact lacks database identity: {path}")
        declared.add(Path(raw).resolve())
    if declared != {database}:
        raise ValueError("SOL target artifact database identity differs")


def _load_bars(database: Path, start_ms: int, end_ms: int) -> dict[int, ProxyMinuteBar]:
    with duckdb.connect(str(database), read_only=True) as connection:
        conflicts = connection.execute(
            _CONFLICT_QUERY, [_SYMBOL, start_ms, end_ms]
        ).fetchone()
        if conflicts is None or int(conflicts[0]) != 0:
            raise ValueError("SOL L2 contains conflicting same-time midpoints")
        frame = connection.execute(_BAR_QUERY, [_SYMBOL, start_ms, end_ms]).fetchdf()
    bars = {int(row.bar_ms): _bar(row) for row in frame.itertuples(index=False)}
    if len(bars) != len(frame):
        raise ValueError("SOL L2 minute identities are not unique")
    return bars


def _bar(row: object) -> ProxyMinuteBar:
    return ProxyMinuteBar(
        timestamp_ms=int(getattr(row, "bar_ms")),
        open=float(getattr(row, "open")),
        high=float(getattr(row, "high")),
        low=float(getattr(row, "low")),
        close=float(getattr(row, "close")),
        snapshot_count=int(getattr(row, "snapshots")),
        first_delay_ms=int(getattr(row, "first_delay_ms")),
        maximum_internal_gap_ms=int(getattr(row, "maximum_internal_gap_ms")),
        end_boundary_age_ms=int(getattr(row, "end_boundary_age_ms")),
    )


def _assessment(report: Mapping[str, object]) -> dict[str, object]:
    thresholds = _mapping(report.get("thresholds_ms"), "thresholds")
    threshold = _mapping(thresholds.get("15000"), "15-second threshold")
    overall = _mapping(threshold.get("overall"), "overall")
    phases = _mapping(threshold.get("by_phase"), "by phase")
    sides = _mapping(threshold.get("by_side"), "by side")
    policies = {
        policy: _policy_assessment(policy, overall, phases, sides)
        for policy in _POLICIES
    }
    supportive = any(
        row["status"] == "research_supportive_not_authorized"
        for row in policies.values()
    )
    return {
        "threshold_ms": 15_000,
        "status": (
            "research_supportive_not_live_authorized"
            if supportive
            else "no_exit_policy_change"
        ),
        "live_change_proposed": False,
        "explicit_approval_requested": False,
        "policies": policies,
    }


def _policy_assessment(
    policy: str,
    overall: Mapping[str, object],
    phases: Mapping[str, object],
    sides: Mapping[str, object],
) -> dict[str, object]:
    pooled = _mapping(overall.get(policy), f"{policy} pooled")
    phase_rows = [_mapping(row, f"{policy} phase") for row in phases.values()]
    side_rows = [_mapping(row, f"{policy} side") for row in sides.values()]
    positive_blocks = sum(_positive_net(row.get(policy)) for row in phase_rows)
    complete = _integer(pooled.get("resolved"), "resolved") == _integer(
        pooled.get("trades"), "trades"
    )
    pooled_robust = _robust_summary(pooled)
    side_robust = len(side_rows) == 2 and all(
        _robust_summary(_mapping(row.get(policy), f"{policy} side summary"))
        for row in side_rows
    )
    block_robust = positive_blocks * 2 > len(phase_rows)
    supportive = complete and pooled_robust and side_robust and block_robust
    return {
        "status": (
            "research_supportive_not_authorized"
            if supportive
            else "rejected_or_technically_incomplete"
        ),
        "complete_paths": complete,
        "pooled_robust": pooled_robust,
        "both_sides_robust": side_robust,
        "positive_blocks": positive_blocks,
        "blocks": len(phase_rows),
    }


def _robust_summary(summary: Mapping[str, object]) -> bool:
    net = _optional_number(summary.get("estimated_net_ex_funding_usd"))
    without = _optional_number(summary.get("net_excluding_largest_winner_usd"))
    profit_factor = _optional_number(summary.get("profit_factor"))
    return (
        net is not None
        and net > 0.0
        and without is not None
        and without > 0.0
        and (profit_factor is None or profit_factor > 1.0)
    )


def _positive_net(value: object) -> bool:
    summary = _mapping(value, "phase policy")
    net = _optional_number(summary.get("estimated_net_ex_funding_usd"))
    return net is not None and net > 0.0


def _selection(
    lifecycles: Sequence[ProxyLifecycle], audit: Mapping[str, object]
) -> dict[str, object]:
    return {
        "symbol": _SYMBOL,
        "strategy_id": "range_onset_bidirectional_v1",
        "source_surface": _SURFACE,
        "source_control": "native_target_none",
        "selected_native_lifecycles": len(lifecycles),
        "blocks": len(_sequence(audit.get("blocks"), "blocks")),
        "policy_selection_performed": False,
    }


def _sources(
    paths: Sequence[Path],
    evidence: Sequence[Mapping[str, object]],
    database: Path,
    database_file: Mapping[str, int],
    bars: Mapping[int, ProxyMinuteBar],
) -> dict[str, object]:
    return {
        "artifacts": [
            {"path": str(path), **dict(identity)}
            for path, identity in zip(paths, evidence, strict=True)
        ],
        "database": _database_identity(database, database_file, bars),
    }


def _database_identity(
    path: Path,
    database_file: Mapping[str, int],
    bars: Mapping[int, ProxyMinuteBar],
) -> dict[str, object]:
    digest = hashlib.sha256()
    for timestamp in sorted(bars):
        row = bars[timestamp]
        digest.update((json.dumps(row.__dict__, sort_keys=True) + "\n").encode())
    return {
        "path": str(path),
        **database_file,
        "selected_rows": len(bars),
        "selected_rows_sha256": digest.hexdigest(),
    }


def _database_file_identity(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {
        "bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def _require_unchanged(
    paths: Sequence[Path],
    evidence: Sequence[Mapping[str, object]],
    database: Path,
    database_before: Mapping[str, int],
) -> None:
    if tuple(file_evidence(path) for path in paths) != tuple(evidence):
        raise RuntimeError("SOL target artifacts changed during evaluation")
    if _database_file_identity(database) != database_before:
        raise RuntimeError("SOL L2 database changed during evaluation")


def _bounds(lifecycles: Sequence[ProxyLifecycle]) -> tuple[int, int]:
    if not lifecycles:
        raise ValueError("SOL proxy selection produced no native lifecycles")
    start = min(row.entry_timestamp_ms for row in lifecycles)
    end = max(row.exit_timestamp_ms for row in lifecycles)
    return start // _MINUTE_MS * _MINUTE_MS, (end // _MINUTE_MS + 1) * _MINUTE_MS


def _limitations() -> list[str]:
    return [
        "the frozen policies were transferred after observing other live giveback",
        "the four source blocks are non-overlapping but are not untouched holdouts",
        "funding and additional exit slippage are excluded from proxy economics",
        "L2 midpoint paths do not prove executable stop fills or mark triggers",
        "this report cannot close, route, size, configure, or submit a trade",
    ]


def _read_mapping(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, f"artifact {path}")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SOL profit-lock {label} is not a mapping")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"SOL profit-lock {label} is not a sequence")
    return value


def _side(value: object) -> str:
    if value not in {"long", "short"}:
        raise ValueError("SOL profit-lock direction must be long or short")
    return str(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"SOL profit-lock {label} must be non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"SOL profit-lock {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"SOL profit-lock {label} must be finite")
    return result


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    return _number(value, "summary value")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only command."""
    args = build_parser().parse_args(argv)
    try:
        run_command(args)
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "output": str(args.output)}, sort_keys=True))
    return 0


_CONFLICT_QUERY = """
SELECT count(*) FROM (
  SELECT ts_exchange_ms
  FROM book_snapshots
  WHERE symbol = ? AND ts_exchange_ms >= ? AND ts_exchange_ms < ?
  GROUP BY ts_exchange_ms
  HAVING min(mid_price) <> max(mid_price)
)
"""

_BAR_QUERY = """
WITH canonical AS (
  SELECT ts_exchange_ms, min(mid_price) AS mid_price
  FROM book_snapshots
  WHERE symbol = ? AND ts_exchange_ms >= ? AND ts_exchange_ms < ?
  GROUP BY ts_exchange_ms
), raw AS (
  SELECT ts_exchange_ms, mid_price,
    (ts_exchange_ms // 60000) * 60000 AS bar_ms,
    lag(ts_exchange_ms) OVER (
      PARTITION BY (ts_exchange_ms // 60000) * 60000 ORDER BY ts_exchange_ms
    ) AS previous_ms
  FROM canonical
)
SELECT bar_ms,
  arg_min(mid_price, ts_exchange_ms) AS open,
  max(mid_price) AS high,
  min(mid_price) AS low,
  arg_max(mid_price, ts_exchange_ms) AS close,
  count(*) AS snapshots,
  min(ts_exchange_ms) - bar_ms AS first_delay_ms,
  coalesce(max(ts_exchange_ms - previous_ms), 0) AS maximum_internal_gap_ms,
  bar_ms + 60000 - max(ts_exchange_ms) AS end_boundary_age_ms
FROM raw GROUP BY bar_ms ORDER BY bar_ms
"""


if __name__ == "__main__":
    raise SystemExit(main())
