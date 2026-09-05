#!/usr/bin/env python3
"""Finalize the frozen HYPE profit-floor transfer after exact resolution."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only floor-finalizer parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closed-path", type=Path, action="append", required=True)
    parser.add_argument("--closed-funded", type=Path, action="append", required=True)
    parser.add_argument("--lifecycle-status", type=Path, required=True)
    parser.add_argument("--resolution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--max-cycles", type=int)
    return parser


def finalize_once(args: argparse.Namespace) -> bool:
    """Publish the complete comparison once exact resolution exists."""
    output = Path(args.output)
    if not Path(args.resolution).exists():
        _write_status(args, "waiting_for_exact_resolution", None)
        return False
    snapshot = _resolution_snapshot(Path(args.resolution))
    resolution = _read_mapping(Path(args.resolution))
    if resolution.get("resolution_status") == "technical_evidence_rejected":
        report = _technical_disposition(args, snapshot)
        _write_status(args, "technical_evidence_rejected_no_floor_promotion", report)
        return True
    if not output.exists():
        _run_transfer(args, snapshot)
    report = _complete_report(output, snapshot)
    _write_status(args, "complete_floor_comparison_published", report)
    return True


def _technical_disposition(args: argparse.Namespace, snapshot: Path) -> Record:
    output = Path(args.output)
    if output.exists():
        report = _read_mapping(output)
        if _matches_technical_disposition(report, args, snapshot):
            return report
        raise FileExistsError(f"HYPE floor output exists: {output}")
    report = {
        "schema_version": 1,
        "mode": "hype_native_mature_profit_floor_transfer_disposition_v1",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "selection_performed": False,
        },
        "policy_id": "a100_floor25_only",
        "decision": "reject_profit_floor_live_change",
        "comparison": {
            "status": "technically_unresolved",
            "trades": 3,
            "floor_net_after_funding_usd": None,
            "floor_net_excluding_largest_winner_usd": None,
        },
        "technical_rejection_reason": (
            "natural_baseline_proxy_exit_not_confirmed_by_official_mark"
        ),
        "source_evidence": {
            "resolution": file_evidence(Path(args.resolution)),
            "prospective_status": file_evidence(snapshot),
            "closed_paths": [file_evidence(Path(path)) for path in args.closed_path],
            "closed_funded": [file_evidence(Path(path)) for path in args.closed_funded],
        },
    }
    write_immutable_json(output, report)
    return report


def _matches_technical_disposition(
    report: Record, args: argparse.Namespace, snapshot: Path
) -> bool:
    contract = _mapping(report.get("contract"), "technical contract")
    sources = _mapping(report.get("source_evidence"), "technical sources")
    resolution = _mapping(sources.get("resolution"), "technical resolution")
    prospective = _mapping(sources.get("prospective_status"), "technical status")
    return (
        report.get("mode") == "hype_native_mature_profit_floor_transfer_disposition_v1"
        and report.get("decision") == "reject_profit_floor_live_change"
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and resolution.get("sha256") == file_evidence(Path(args.resolution))["sha256"]
        and prospective.get("sha256") == file_evidence(snapshot)["sha256"]
    )


def run_loop(args: argparse.Namespace) -> bool:
    """Poll within explicit bounds until the final comparison is available."""
    _validate_loop(args)
    cycle = 0
    while args.max_cycles is None or cycle < args.max_cycles:
        cycle += 1
        if finalize_once(args):
            return True
        if args.max_cycles is None or cycle < args.max_cycles:
            time.sleep(args.poll_seconds)
    return False


def _run_transfer(args: argparse.Namespace, snapshot: Path) -> None:
    script = Path(__file__).with_name("hype_native_profit_floor_transfer.py")
    command = [sys.executable, str(script)]
    for path, funded in zip(args.closed_path, args.closed_funded, strict=True):
        command.extend(("--closed-path", str(path), "--closed-funded", str(funded)))
    command.extend(
        (
            "--lifecycle-status",
            str(snapshot),
            "--resolution",
            str(args.resolution),
            "--output",
            str(args.output),
            "--immutable",
        )
    )
    subprocess.run(command, check=True, capture_output=True, text=True)


def _complete_report(path: Path, snapshot: Path) -> Record:
    report = _read_mapping(path)
    contract = _mapping(report.get("contract"), "floor contract")
    comparison = _mapping(report.get("comparison"), "floor comparison")
    sources = _mapping(report.get("source_evidence"), "floor source evidence")
    prospective = _mapping(sources.get("prospective_status"), "prospective status")
    if (
        report.get("mode") != "hype_native_mature_profit_floor_transfer_v1"
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or comparison.get("status") != "complete"
        or prospective.get("sha256") != file_evidence(snapshot)["sha256"]
    ):
        raise ValueError("HYPE floor final output is not a complete report-only result")
    return report


def _resolution_snapshot(resolution: Path) -> Path:
    report = _read_mapping(resolution)
    evidence = _mapping(report.get("evidence"), "resolution evidence")
    source = _mapping(evidence.get("lifecycle_status"), "resolved lifecycle status")
    raw_path = source.get("path")
    expected = source.get("sha256")
    if not isinstance(raw_path, str) or not isinstance(expected, str):
        raise ValueError("HYPE floor resolution lacks lifecycle source identity")
    snapshot = Path(raw_path)
    if file_evidence(snapshot)["sha256"] != expected:
        raise RuntimeError("HYPE floor resolved lifecycle snapshot changed")
    return snapshot


def _write_status(args: argparse.Namespace, state: str, report: Record | None) -> None:
    comparison = (
        {} if report is None else _mapping(report.get("comparison"), "comparison")
    )
    payload = {
        "schema_version": 1,
        "mode": "hype_native_profit_floor_finalizer_report_only",
        "report_only": True,
        "execution_authority": "none",
        "state": state,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "trades": comparison.get("trades"),
        "output_evidence": None if report is None else file_evidence(Path(args.output)),
    }
    write_atomic_json(Path(args.status), payload)


def _validate_loop(args: argparse.Namespace) -> None:
    if len(args.closed_path) != len(args.closed_funded):
        raise ValueError("closed HYPE path and funded artifact counts differ")
    if args.poll_seconds <= 0.0 or (
        args.max_cycles is not None and args.max_cycles <= 0
    ):
        raise ValueError("HYPE floor finalizer polling bounds must be positive")


def _read_mapping(path: Path) -> Record:
    return _mapping(json.loads(path.read_text(encoding="utf-8")), f"artifact {path}")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"HYPE floor {label} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bounded report-only floor finalizer."""
    args = build_parser().parse_args(argv)
    try:
        complete = run_loop(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "complete": complete}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
