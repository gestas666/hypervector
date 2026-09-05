#!/usr/bin/env python3
"""Publish immutable SP500 profit-lock evidence from causal L2 midpoint bars."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final, Mapping

import duckdb

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_profit_lock_l2_proxy import (
    ProxyLifecycle,
    ProxyMinuteBar,
    build_profit_lock_proxy_report,
)
from hypervector.research.sp500_profit_lock_evidence import (
    assess_sp500_profit_lock,
    load_sp500_profit_lock_lifecycles,
    profit_lock_lifecycle_bounds,
    sp500_profit_lock_selection,
)

_THRESHOLDS_MS: Final = (5_000, 10_000, 15_000, 30_000, 60_000)
_MINUTE_MS: Final = 60_000


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
    lifecycles = load_sp500_profit_lock_lifecycles(trades_path)
    start_ms, end_ms = _bounds(lifecycles)
    bars = _load_bars(database_path, start_ms, end_ms)
    report = build_profit_lock_proxy_report(lifecycles, bars, _THRESHOLDS_MS)
    report["assessment"] = assess_sp500_profit_lock(report)
    report.update(
        {
            "selection": sp500_profit_lock_selection(lifecycles),
            "data_quality": _quality(lifecycles, bars, start_ms, end_ms),
            "sources": {
                "trades": trade_identity,
                "database": _database_identity(database_path, bars),
            },
        }
    )
    if _file_identity(trades_path) != trade_identity:
        raise RuntimeError("SP500 lifecycle input changed during evaluation")
    write_immutable_json(output, report)
    return 0


def _assessment(report: Mapping[str, object]) -> dict[str, object]:
    return assess_sp500_profit_lock(report)


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
    start, end = profit_lock_lifecycle_bounds(lifecycles)
    return start // _MINUTE_MS * _MINUTE_MS, (end // _MINUTE_MS + 1) * _MINUTE_MS


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
    return {"path": str(path), **file_evidence(path)}


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
