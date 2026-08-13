#!/usr/bin/env python3
"""Publish immutable SP500 profit-lock evidence from causal L2 midpoint bars."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Final, Mapping

import duckdb
import pandas as pd

from hypervector.research.cohort_profit_lock_l2_proxy import (
    ProxyLifecycle,
    ProxyMinuteBar,
    build_profit_lock_proxy_report,
)

_STRATEGY: Final = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
_SYMBOL: Final = "xyz:SP500"
_FRICTION: Final = "stress"
_PHASES: Final = ("development", "validation")
_THRESHOLDS_MS: Final = (5_000, 10_000, 15_000, 30_000, 60_000)
_MINUTE_MS: Final = 60_000
_REQUIRED: Final = frozenset(
    {
        "strategy_id",
        "symbol",
        "phase",
        "friction",
        "direction",
        "entry_time_utc",
        "exit_time_utc",
        "entry_price",
        "exit_price",
        "quantity",
        "gross_pnl_usd",
        "fees_usd",
    }
)


def parse_args() -> argparse.Namespace:
    """Parse report-only command arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path(
            "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.trades.parquet"
        ),
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/research/hip3_market.duckdb")
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run_command(args: argparse.Namespace) -> int:
    """Build and publish one immutable report without execution authority."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    trades_path = Path(args.trades)
    database_path = Path(args.database)
    trade_identity = _file_identity(trades_path)
    lifecycles = _load_lifecycles(trades_path)
    start_ms, end_ms = _bounds(lifecycles)
    bars = _load_bars(database_path, start_ms, end_ms)
    report = build_profit_lock_proxy_report(lifecycles, bars, _THRESHOLDS_MS)
    report["assessment"] = _assessment(report)
    report.update(
        {
            "selection": _selection(lifecycles),
            "data_quality": _quality(lifecycles, bars, start_ms, end_ms),
            "sources": {
                "trades": trade_identity,
                "database": _database_identity(database_path, bars),
            },
        }
    )
    if _file_identity(trades_path) != trade_identity:
        raise RuntimeError("SP500 lifecycle input changed during evaluation")
    _write_exclusive(output, report)
    return 0


def _assessment(report: Mapping[str, object]) -> dict[str, object]:
    thresholds = _mapping(report.get("thresholds_ms"), "thresholds")
    threshold = _mapping(thresholds.get("15000"), "15-second threshold")
    phases = _mapping(threshold.get("by_phase"), "phase summaries")
    development = _mapping(phases.get("development"), "development summary")
    validation = _mapping(phases.get("validation"), "validation summary")
    dispositions = {
        policy: _policy_disposition(
            _mapping(development.get(policy), f"{policy} development"),
            _mapping(validation.get(policy), f"{policy} validation"),
        )
        for policy in (
            "a25_floor15_trail10",
            "a40_floor15_trail20",
            "a60_floor15_trail30",
        )
    }
    supportive = any(
        value == "research_supportive_not_authorized" for value in dispositions.values()
    )
    return {
        "overall_disposition": (
            "research_supportive_not_live_authorized"
            if supportive
            else "no_exit_policy_change"
        ),
        **dispositions,
        "execution_effect": "report_only",
    }


def _policy_disposition(
    development: Mapping[str, object], validation: Mapping[str, object]
) -> str:
    if not _supportive(validation):
        return "rejected_validation_after_cost_negative"
    if not _supportive(development):
        return "withheld_no_cross_partition_support"
    return "research_supportive_not_authorized"


def _supportive(summary: Mapping[str, object]) -> bool:
    net = summary.get("estimated_net_ex_funding_usd")
    profit_factor = summary.get("profit_factor")
    valid_net = isinstance(net, (int, float)) and not isinstance(net, bool) and net > 0
    valid_pf = profit_factor is None or (
        isinstance(profit_factor, (int, float))
        and not isinstance(profit_factor, bool)
        and profit_factor > 1
    )
    return valid_net and valid_pf


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SP500 profit-lock {label} is not a mapping")
    return value


def _load_lifecycles(path: Path) -> tuple[ProxyLifecycle, ...]:
    frame = pd.read_parquet(path)
    missing = sorted(_REQUIRED.difference(frame.columns))
    if missing:
        raise ValueError(f"SP500 lifecycle evidence missing columns: {missing}")
    selected = frame[
        (frame["strategy_id"] == _STRATEGY)
        & (frame["symbol"] == _SYMBOL)
        & (frame["friction"] == _FRICTION)
        & frame["phase"].isin(_PHASES)
    ].copy()
    if selected.empty:
        raise ValueError("SP500 profit-lock selection produced no lifecycles")
    selected["entry_time_utc"] = pd.to_datetime(selected["entry_time_utc"], utc=True)
    selected["exit_time_utc"] = pd.to_datetime(selected["exit_time_utc"], utc=True)
    rows = tuple(_lifecycle(row) for row in selected.itertuples(index=False))
    identities = [row.lifecycle_id for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("SP500 profit-lock lifecycle identities are not unique")
    return rows


def _lifecycle(row: object) -> ProxyLifecycle:
    entry = getattr(row, "entry_time_utc")
    exit_time = getattr(row, "exit_time_utc")
    entry_ms = int(entry.timestamp() * 1_000)
    return ProxyLifecycle(
        lifecycle_id=f"{_SYMBOL}:{getattr(row, 'phase')}:{entry_ms}",
        phase=str(getattr(row, "phase")),
        side=str(getattr(row, "direction")),
        entry_timestamp_ms=entry_ms,
        exit_timestamp_ms=int(exit_time.timestamp() * 1_000),
        entry_price=float(getattr(row, "entry_price")),
        exit_price=float(getattr(row, "exit_price")),
        quantity=float(getattr(row, "quantity")),
        gross_pnl_usd=float(getattr(row, "gross_pnl_usd")),
        fees_usd=float(getattr(row, "fees_usd")),
    )


def _load_bars(database: Path, start_ms: int, end_ms: int) -> dict[int, ProxyMinuteBar]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        frame = connection.execute(_BAR_QUERY, [start_ms, end_ms]).fetchdf()
    finally:
        connection.close()
    bars = {int(row.bar_ms): _bar(row) for row in frame.itertuples(index=False)}
    if len(bars) != len(frame):
        raise ValueError("SP500 L2 minute identities are not unique")
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


def _bounds(lifecycles: tuple[ProxyLifecycle, ...]) -> tuple[int, int]:
    start = min(row.entry_timestamp_ms for row in lifecycles)
    end = max(row.exit_timestamp_ms for row in lifecycles)
    return start // _MINUTE_MS * _MINUTE_MS, (end // _MINUTE_MS + 1) * _MINUTE_MS


def _selection(lifecycles: tuple[ProxyLifecycle, ...]) -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY,
        "symbol": _SYMBOL,
        "friction": _FRICTION,
        "phases": list(_PHASES),
        "selected_lifecycles": len(lifecycles),
    }


def _quality(
    lifecycles: tuple[ProxyLifecycle, ...],
    bars: dict[int, ProxyMinuteBar],
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    return {
        "intended_lifecycle_grain": "strategy-symbol-phase-friction-entry_time",
        "lifecycle_count": len(lifecycles),
        "l2_minute_count": len(bars),
        "query_start_ms": start_ms,
        "query_end_ms_exclusive": end_ms,
        "completeness_thresholds_ms": list(_THRESHOLDS_MS),
    }


def _database_identity(
    path: Path, bars: dict[int, ProxyMinuteBar]
) -> dict[str, object]:
    stat = path.stat()
    payload = [bars[key].__dict__ for key in sorted(bars)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
        "selected_rows": len(payload),
        "selected_rows_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _file_identity(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _write_exclusive(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


_BAR_QUERY = """
WITH raw AS (
  SELECT ts_exchange_ms, mid_price,
    (ts_exchange_ms // 60000) * 60000 AS bar_ms,
    lag(ts_exchange_ms) OVER (
      PARTITION BY (ts_exchange_ms // 60000) * 60000 ORDER BY ts_exchange_ms
    ) AS previous_ms
  FROM book_snapshots
  WHERE symbol = 'xyz:SP500' AND ts_exchange_ms >= ? AND ts_exchange_ms < ?
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


def main() -> int:
    """Run the immutable report-only command."""
    return run_command(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
