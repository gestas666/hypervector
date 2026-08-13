#!/usr/bin/env python3
"""Compare research target lifecycles with the production event runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import cast

from hypervector.research.source_follow_execution_parity import (
    SourceLifecycleExecution,
    SourceLifecycleSpec,
    load_archive_events,
    replay_source_lifecycle,
)


def parse_args() -> argparse.Namespace:
    """Parse bounded report-only replay arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--candidate", default="alloc50_lev30")
    parser.add_argument("--maximum-trades", type=int, default=5)
    parser.add_argument("--exit-extension-seconds", type=float, default=3_600.0)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Run bounded production-runtime parity and write immutable evidence."""
    args = parse_args()
    if args.maximum_trades <= 0 or args.exit_extension_seconds <= 0.0:
        raise ValueError("trade limit and exit extension must be positive")
    source = _object(_load_json(args.artifact), "artifact")
    expected = _target_trades(source, args.candidate)[: args.maximum_trades]
    if not expected:
        raise ValueError("source artifact has no target-completed trades")
    comparisons = [
        _replay_trade(
            args.database,
            trade,
            exit_extension_seconds=args.exit_extension_seconds,
        )
        for trade in expected
    ]
    payload = {
        "schema": "hypervelocity_source_execution_parity_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "database_path": str(args.database.resolve()),
        "source_artifact": _evidence(args.artifact),
        "candidate": args.candidate,
        "comparison_scope": "target_completed_lifecycles_only",
        "maximum_trades": args.maximum_trades,
        "exit_extension_seconds": args.exit_extension_seconds,
        "summary": _summary(comparisons),
        "comparisons": comparisons,
        "limitations": [
            "This check compares maker entry/target execution, not mark liquidation.",
            "Funding and portfolio-continuity PnL are intentionally excluded.",
            "Archive receipt time is unavailable, so exchange time is used as receipt time.",
            "Displayed queue is a public-depth proxy; private cancellations remain unknown.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    return 0


def _replay_trade(
    database: Path,
    expected: dict[str, object],
    *,
    exit_extension_seconds: float,
) -> dict[str, object]:
    signal = _text(expected, "signal_time_utc")
    expected_exit = _text(expected, "exit_time_utc")
    end = _utc(expected_exit) + timedelta(seconds=exit_extension_seconds)
    events = load_archive_events(
        database,
        symbol="BTC",
        start_utc=signal,
        end_utc=end.isoformat(),
    )
    quantity = _quantize_down(_number(expected, "quantity"), decimals=5)
    result = replay_source_lifecycle(
        events,
        SourceLifecycleSpec(signal, "short", quantity),
    )
    return {
        "signal_time_utc": signal,
        "expected": expected,
        "production": result.to_dict(),
        "differences": _differences(expected, result),
        "archive_event_count": len(events),
    }


def _differences(
    expected: dict[str, object],
    actual: SourceLifecycleExecution,
) -> dict[str, object]:
    expected_entry = _text(expected, "entry_time_utc")
    expected_exit = _text(expected, "exit_time_utc")
    return {
        "completed": actual.status == "completed",
        "submission_delay_seconds": _seconds_between(
            _text(expected, "submitted_time_utc"), actual.submitted_at
        ),
        "entry_completion_delay_seconds": _seconds_between(
            expected_entry, actual.entry_completed_at
        ),
        "exit_completion_delay_seconds": _seconds_between(
            expected_exit, actual.exit_completed_at
        ),
        "entry_price_difference": _difference(
            _number(expected, "entry_price"), actual.entry_price
        ),
        "exit_price_difference": _difference(
            _number(expected, "exit_price"), actual.exit_price
        ),
        "quantity_difference": actual.entry_filled_quantity
        - _number(expected, "quantity"),
        "used_partial_entry_fills": actual.entry_fill_count > 1,
        "used_partial_exit_fills": actual.exit_fill_count > 1,
    }


def _summary(comparisons: list[dict[str, object]]) -> dict[str, object]:
    differences = [
        _object(comparison["differences"], "differences") for comparison in comparisons
    ]
    completed = sum(item["completed"] is True for item in differences)
    partial = sum(
        _object(comparison["production"], "production").get("status")
        == "partial_completed"
        for comparison in comparisons
    )
    return {
        "expected_target_count": len(comparisons),
        "production_completed_count": completed,
        "production_partial_completed_count": partial,
        "completion_parity": completed == len(comparisons),
        "median_entry_completion_delay_seconds": _median_field(
            differences, "entry_completion_delay_seconds"
        ),
        "median_exit_completion_delay_seconds": _median_field(
            differences, "exit_completion_delay_seconds"
        ),
        "partial_entry_lifecycles": sum(
            item["used_partial_entry_fills"] is True for item in differences
        ),
        "partial_exit_lifecycles": sum(
            item["used_partial_exit_fills"] is True for item in differences
        ),
    }


def _target_trades(
    artifact: dict[str, object],
    candidate: str,
) -> list[dict[str, object]]:
    fresh = _object(artifact.get("fresh"), "fresh")
    candidates = _object(fresh.get("candidates"), "candidates")
    selected = _object(candidates.get(candidate), candidate)
    replay = _object(selected.get("replay"), "replay")
    trades = replay.get("trades")
    if not isinstance(trades, list):
        raise ValueError("candidate replay trades must be a list")
    return [
        cast(dict[str, object], trade)
        for trade in trades
        if isinstance(trade, dict) and trade.get("status") == "target_completed"
    ]


def _median_field(rows: list[dict[str, object]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    return median(values) if values else None


def _seconds_between(start: str, end: str | None) -> float | None:
    return None if end is None else (_utc(end) - _utc(start)).total_seconds()


def _difference(expected: float, actual: float | None) -> float | None:
    return None if actual is None else actual - expected


def _quantize_down(value: float, *, decimals: int) -> float:
    factor = 10**decimals
    return math.floor(value * factor) / factor


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0.0:
        raise ValueError("parity timestamps must be UTC")
    return parsed


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return value


def _number(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _evidence(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
