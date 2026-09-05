#!/usr/bin/env python3
"""Publish an immutable report-only HIP-3 REST/websocket mark comparison."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import NamedTuple, cast

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_mark_source_parity import (
    REST_SOURCE,
    WEBSOCKET_SOURCE,
    Hip3MarkParitySpec,
    build_hip3_mark_source_parity,
)

Record = dict[str, object]
_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")


class _SourceSnapshot(NamedTuple):
    """One frozen immutable parquet file set and its aggregate evidence."""

    paths: tuple[Path, ...]
    evidence: Record
    exact_files: tuple[tuple[Path, Record], ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit local-only report command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--maximum-pair-age-ms", type=int, default=250)
    parser.add_argument("--minimum-pairs", type=int, default=100)
    parser.add_argument("--maximum-mark-difference-bps", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> Record:
    """Freeze exact local files, compare both sources, and publish once."""
    output = Path(args.output)
    _require_new_output(output)
    capture_date = date.fromisoformat(str(args.date))
    symbols = tuple(args.symbols or _DEFAULT_SYMBOLS)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("HIP-3 parity symbols must be unique and nonempty")
    specs = {symbol: _spec(args, symbol) for symbol in symbols}
    snapshots = {
        symbol: _source_snapshot(Path(args.data_root), symbol, capture_date)
        for symbol in symbols
    }
    reports = {
        symbol: build_hip3_mark_source_parity(
            _load_rows(snapshots[symbol].paths), specs[symbol]
        )
        for symbol in symbols
    }
    report = _combined_report(capture_date, symbols, specs, snapshots, reports)
    _require_unchanged_snapshots(snapshots)
    write_immutable_json(output, report)
    return report


def _spec(args: argparse.Namespace, symbol: str) -> Hip3MarkParitySpec:
    return Hip3MarkParitySpec(
        symbol=symbol,
        maximum_pair_age_ms=int(args.maximum_pair_age_ms),
        minimum_pairs=int(args.minimum_pairs),
        maximum_mark_difference_bps=float(args.maximum_mark_difference_bps),
    )


def _source_snapshot(root: Path, symbol: str, capture_date: date) -> _SourceSnapshot:
    directory = (
        root
        / "cache/events/hyperliquid"
        / symbol
        / capture_date.isoformat()
        / "asset_context.parquet"
    )
    paths = tuple(sorted(directory.glob("*.parquet")))
    if not paths:
        raise FileNotFoundError(f"HIP-3 mark source files are missing: {directory}")
    exact = tuple((path, file_evidence(path)) for path in paths)
    entries = [_manifest_entry(root, path, evidence) for path, evidence in exact]
    rendered = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    evidence: Record = {
        "file_count": len(entries),
        "total_bytes": sum(_integer(item, "bytes") for item in entries),
        "manifest_sha256": hashlib.sha256(rendered).hexdigest(),
        "files": entries,
    }
    return _SourceSnapshot(paths, evidence, exact)


def _manifest_entry(root: Path, path: Path, evidence: Mapping[str, object]) -> Record:
    relative = path.resolve().relative_to(root.resolve())
    return {"path": str(relative), **dict(evidence)}


def _load_rows(paths: tuple[Path, ...]) -> list[Record]:
    columns = ["symbol", "received_ts_ns", "mark_price", "source"]
    frame = pd.read_parquet([str(path) for path in paths], columns=columns)
    selected = frame.loc[frame["source"].isin((REST_SOURCE, WEBSOCKET_SOURCE)), columns]
    if selected.empty:
        raise ValueError("HIP-3 mark snapshot contains neither required source")
    return cast(list[Record], selected.to_dict(orient="records"))


def _combined_report(
    capture_date: date,
    symbols: tuple[str, ...],
    specs: Mapping[str, Hip3MarkParitySpec],
    snapshots: Mapping[str, _SourceSnapshot],
    reports: Mapping[str, Record],
) -> Record:
    resolved = all(report["status"] == "resolved" for report in reports.values())
    passed = resolved and all(
        report["parity_passed"] is True for report in reports.values()
    )
    status = "resolved_pass" if passed else "resolved_transport_mismatch"
    if not resolved:
        status = "insufficient_overlap"
    return {
        "schema_version": "v51_hip3_mark_source_parity_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "parity_passed": passed,
        "symbols": list(symbols),
        "capture_date": capture_date.isoformat(),
        "thresholds": _thresholds(specs),
        "reports": dict(reports),
        "input_evidence": {symbol: snapshots[symbol].evidence for symbol in symbols},
        "generator_identity": _generator_identity(),
        "disposition": _disposition(status),
        "execution_authority": "none",
        "report_only": True,
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _thresholds(specs: Mapping[str, Hip3MarkParitySpec]) -> Record:
    selected = next(iter(specs.values()))
    return {
        "pairing": "one_to_one_nearest_local_receipt",
        "difference_metric": "symmetric_midpoint_relative_bps",
        "maximum_pair_age_ms": selected.maximum_pair_age_ms,
        "minimum_pairs_per_symbol": selected.minimum_pairs,
        "maximum_mark_difference_bps": selected.maximum_mark_difference_bps,
    }


def _disposition(status: str) -> str:
    if status == "resolved_pass":
        return "strict_transport_parity_observed_no_live_change_authorized"
    if status == "resolved_transport_mismatch":
        return "strict_source_substitution_not_validated_investigate_mismatches"
    return "collect_more_independent_overlap"


def _generator_identity() -> Record:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_mark_source_parity.py",
        root / "src/hypervector/data/hip3_mark_snapshot_recorder.py",
        root / "src/hypervector/data/event_archive.py",
        root / "src/hypervector/data/hl_events.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_unchanged_snapshots(snapshots: Mapping[str, _SourceSnapshot]) -> None:
    for snapshot in snapshots.values():
        for path, expected in snapshot.exact_files:
            if file_evidence(path) != expected:
                raise ValueError(f"HIP-3 mark source changed during analysis: {path}")


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"HIP-3 mark parity output already exists: {path}")


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"HIP-3 parity {key} must be an integer")
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local comparison and print only safe report metadata."""
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
