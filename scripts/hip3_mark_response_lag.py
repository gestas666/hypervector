#!/usr/bin/env python3
"""Publish immutable causal REST/WebSocket HIP-3 mark-lag evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.local_parquet_snapshot import LocalParquetSnapshot
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_mark_response_lag import (
    Hip3MarkResponseLagSpec,
    build_hip3_mark_response_lag,
)

Record = dict[str, object]
_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_COLUMNS = [
    "symbol",
    "received_ts_ns",
    "mark_price",
    "oracle_price",
    "funding_rate_hourly",
    "open_interest",
    "mid_price",
    "source",
]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit local-only report command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--minimum-rest-rows", type=int, default=500)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> Record:
    """Freeze local rows, measure causal lag, and publish exactly once."""
    output = Path(args.output)
    _require_new_output(output)
    root = Path(args.data_root)
    capture_date = date.fromisoformat(str(args.date))
    symbols = _symbols(args)
    snapshots = {symbol: _snapshot(root, symbol, capture_date) for symbol in symbols}
    reports = {
        symbol: build_hip3_mark_response_lag(
            _rows(snapshots[symbol]),
            Hip3MarkResponseLagSpec(symbol, int(args.minimum_rest_rows)),
        )
        for symbol in symbols
    }
    report = _report(capture_date, symbols, snapshots, reports)
    for snapshot in snapshots.values():
        snapshot.require_unchanged()
    write_immutable_json(output, report)
    return report


def _symbols(args: argparse.Namespace) -> tuple[str, ...]:
    symbols = tuple(args.symbols or _DEFAULT_SYMBOLS)
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("HIP-3 lag symbols must be unique and nonempty")
    return symbols


def _snapshot(root: Path, symbol: str, capture_date: date) -> LocalParquetSnapshot:
    directory = (
        root
        / "cache/events/hyperliquid"
        / symbol
        / capture_date.isoformat()
        / "asset_context.parquet"
    )
    return LocalParquetSnapshot.from_directory(root, directory)


def _rows(snapshot: LocalParquetSnapshot) -> list[Record]:
    frame = snapshot.load(_COLUMNS)
    return cast(list[Record], frame.to_dict(orient="records"))


def _report(
    capture_date: date,
    symbols: tuple[str, ...],
    snapshots: Mapping[str, LocalParquetSnapshot],
    reports: Mapping[str, Record],
) -> Record:
    resolved = all(report["status"] == "resolved" for report in reports.values())
    mismatch = any(
        report["disposition"] == "rest_receipt_cannot_certify_exact_mark_time"
        for report in reports.values()
    )
    status = "insufficient_overlap"
    disposition = "collect_more_overlap"
    if resolved and mismatch:
        status = "resolved_rest_receipt_not_exact"
        disposition = "keep_rest_supplemental_and_exact_path_unresolved"
    elif resolved:
        status = "resolved_no_mismatch_observed"
        disposition = "do_not_promote_source_from_negative_mismatch_sample"
    return {
        "schema_version": "v51_hip3_mark_response_lag_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "disposition": disposition,
        "symbols": list(symbols),
        "capture_date": capture_date.isoformat(),
        "reports": dict(reports),
        "input_evidence": {symbol: snapshots[symbol].evidence for symbol in symbols},
        "generator_identity": _generator_identity(),
        "execution_authority": "none",
        "report_only": True,
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _generator_identity() -> Record:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/data/local_parquet_snapshot.py",
        root / "src/hypervector/research/hip3_mark_response_lag.py",
        root / "src/hypervector/research/hip3_mark_source_parity.py",
        root / "src/hypervector/data/hip3_mark_snapshot_recorder.py",
        root / "src/hypervector/data/event_archive.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"HIP-3 mark lag output already exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the comparison and print only safe report metadata."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "status": report["status"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
