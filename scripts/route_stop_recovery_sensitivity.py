#!/usr/bin/env python3
"""Publish one immutable report-only route stop-recovery sensitivity."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_stop_recovery_sensitivity import (
    build_stop_recovery_sensitivity,
)

Record = Mapping[str, object]
_DEFAULT_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_DEFAULT_WIDTHS = (60.0, 80.0, 100.0, 120.0)


def build_parser() -> argparse.ArgumentParser:
    """Build explicit immutable source, route, and horizon arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_DEFAULT_CHECKPOINT)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--assessment-horizon-minutes", type=int, required=True)
    parser.add_argument(
        "--stop-width-bps", action="append", dest="stop_widths", type=float
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Read, filter, verify, and publish one execution-incapable report."""
    source = Path(args.checkpoint)
    output = Path(args.out)
    if source.resolve() == output.resolve():
        raise ValueError("stop-recovery output must differ from its checkpoint")
    if output.exists():
        raise FileExistsError(f"immutable JSON output exists: {output}")
    raw = source.read_bytes()
    checkpoint = _mapping(json.loads(raw), "checkpoint")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    history = _mapping(reflections.get("all_time_live"), "all-time live history")
    selected = _selected_trades(
        _records(history.get("trades"), "all-time trades"),
        str(args.strategy_id),
        str(args.symbol),
    )
    report = build_stop_recovery_sensitivity(
        selected,
        stop_widths_bps=tuple(args.stop_widths or _DEFAULT_WIDTHS),
        assessment_horizon_minutes=int(args.assessment_horizon_minutes),
    )
    report.update(_metadata(args, checkpoint, source, raw, selected))
    if source.read_bytes() != raw:
        raise RuntimeError("stop-recovery checkpoint changed during evaluation")
    write_immutable_json(output, report)
    return report


def _selected_trades(
    rows: Sequence[Record], strategy_id: str, symbol: str
) -> tuple[Record, ...]:
    selected = tuple(
        row
        for row in rows
        if row.get("strategy_id") == strategy_id
        and row.get("symbol") == symbol
        and row.get("exit_reason") == "protective_stop"
    )
    if not selected:
        raise ValueError("route has no attributable protective-stop trades")
    return selected


def _metadata(
    args: argparse.Namespace,
    checkpoint: Record,
    source: Path,
    raw: bytes,
    selected: Sequence[Record],
) -> dict[str, object]:
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "route": {"strategy_id": str(args.strategy_id), "symbol": str(args.symbol)},
        "source": {
            "path": str(source.resolve()),
            "bytes": len(raw),
            "sha256": file_evidence(source)["sha256"],
            "generated_at_utc": checkpoint.get("generated_at_utc"),
        },
        "embedded_route_trade_count": len(selected),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be a list of objects")
    return tuple(cast(list[dict[str, object]], value))


def main(argv: Sequence[str] | None = None) -> int:
    """Publish the report and print its non-executable state."""
    args = build_parser().parse_args(argv)
    report = run_report(args)
    print(
        json.dumps(
            {
                "execution_authority": "none",
                "output": str(args.out),
                "protective_stop_trades": report["summary"]["protective_stop_trades"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
