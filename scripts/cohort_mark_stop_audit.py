#!/usr/bin/env python3
"""Publish an immutable exact-mark stop-path audit for one cohort lifecycle."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    text,
)
from hypervector.research.cohort_mark_stop_path import (
    MarkStopPathSpec,
    build_mark_stop_path,
)
from hypervector.research.hip3_shadow_lifecycle_sources import FrozenHip3MarkArchive

Record = dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the local, report-only audit command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--lifecycle-id", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--as-of-time-ms", type=int, required=True)
    parser.add_argument("--maximum-gap-ms", type=int, default=5_000)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(args: argparse.Namespace) -> Record:
    """Freeze exact audit and mark inputs, analyze them, and publish once."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"cohort mark-stop output already exists: {output}")
    audit_path = Path(args.audit)
    audit_evidence = _path_evidence(audit_path)
    audit = _load_json(audit_path)
    lifecycle = _open_lifecycle(audit, str(args.lifecycle_id))
    identity = _lifecycle_identity(lifecycle)
    spec = _spec(identity, int(args.as_of_time_ms), int(args.maximum_gap_ms))
    source = FrozenHip3MarkArchive()
    rows, mark_evidence = source.load(
        data_root=Path(args.data_root),
        symbol=spec.symbol,
        start_ms=spec.entry_time_ms,
        end_ms=spec.as_of_time_ms,
    )
    generator = _generator_identity()
    report = _report(audit, identity, audit_evidence, mark_evidence, rows, spec)
    _require_unchanged(audit_path, audit_evidence, source, mark_evidence, generator)
    write_immutable_json(output, report)
    return report


def _report(
    audit: Mapping[str, object],
    identity: Record,
    audit_evidence: Record,
    mark_evidence: Record,
    rows: Sequence[Mapping[str, object]],
    spec: MarkStopPathSpec,
) -> Record:
    path = build_mark_stop_path(rows, spec)
    return {
        "schema_version": "cohort_mark_stop_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "report_only_exact_venue_mark_stop_path",
        "run_identity": _run_identity(audit),
        "lifecycle_identity": identity,
        "mark_stop_path": path,
        "assessment": _assessment(path),
        "input_evidence": {"audit": audit_evidence, "marks": mark_evidence},
        "generator_identity": _generator_identity(),
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "limitations": [
            "Observed websocket marks cannot rule out a transient move inside an unobserved receipt gap.",
            "The report diagnoses stop-path evidence and does not establish strategy profitability.",
            "No order, position, route, strategy, sizing, leverage, or risk setting is changed.",
        ],
    }


def _open_lifecycle(
    audit: Mapping[str, object], lifecycle_id: str
) -> Mapping[str, object]:
    reflections = mapping(audit.get("open_trade_reflections"), "open reflections")
    trades = mapping_list(reflections.get("trades"), "open trades")
    matches = [row for row in trades if row.get("lifecycle_id") == lifecycle_id]
    if len(matches) != 1:
        raise ValueError("audit must contain exactly one open lifecycle with that id")
    return matches[0]


def _lifecycle_identity(lifecycle: Mapping[str, object]) -> Record:
    entry = mapping(lifecycle.get("entry"), "lifecycle entry")
    stop = mapping(lifecycle.get("protective_stop"), "protective stop")
    return {
        "lifecycle_id": text(lifecycle.get("lifecycle_id"), "lifecycle id"),
        "source_run_id": text(lifecycle.get("source_run_id"), "source run id"),
        "strategy_id": text(lifecycle.get("strategy_id"), "strategy id"),
        "symbol": text(lifecycle.get("symbol"), "symbol"),
        "side": text(lifecycle.get("side"), "side"),
        "entry_time_ms": nonnegative_int(entry.get("venue_timestamp_ms"), "entry time"),
        "entry_price": number(entry.get("price"), "entry price"),
        "entry_size": number(entry.get("size"), "entry size"),
        "stop_oid": nonnegative_int(stop.get("oid"), "stop oid"),
        "stop_price": number(stop.get("trigger_price"), "stop price"),
    }


def _spec(
    identity: Mapping[str, object], as_of_ms: int, maximum_gap_ms: int
) -> MarkStopPathSpec:
    return MarkStopPathSpec(
        symbol=text(identity.get("symbol"), "symbol"),
        side=text(identity.get("side"), "side"),
        entry_time_ms=nonnegative_int(identity.get("entry_time_ms"), "entry time"),
        as_of_time_ms=as_of_ms,
        stop_price=number(identity.get("stop_price"), "stop price"),
        maximum_gap_ms=maximum_gap_ms,
    )


def _run_identity(audit: Mapping[str, object]) -> Record:
    run = mapping(audit.get("run"), "audit run")
    return {
        "run_id": text(run.get("run_id"), "run id"),
        "profile_id": text(run.get("profile_id"), "profile id"),
        "profile_fingerprint": text(
            run.get("profile_fingerprint"), "profile fingerprint"
        ),
    }


def _assessment(path: Mapping[str, object]) -> Record:
    crossed = path.get("observed_stop_crossed") is True
    continuous = path.get("continuous_at_declared_gap_bound") is True
    if crossed:
        disposition = "observed_mark_stop_cross_requires_execution_reconciliation"
    elif continuous:
        disposition = "no_observed_cross_at_declared_sampling_bound"
    else:
        disposition = "no_observed_cross_but_mark_continuity_unresolved"
    return {
        "disposition": disposition,
        "implementation_defect_established": False,
        "unobserved_cross_excluded": False,
    }


def _load_json(path: Path) -> Mapping[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("cohort mark-stop audit input must be an object")
    return cast(Mapping[str, object], raw)


def _path_evidence(path: Path) -> Record:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _generator_identity() -> Record:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/cohort_mark_stop_path.py",
        root / "src/hypervector/research/hip3_shadow_lifecycle_sources.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_unchanged(
    audit_path: Path,
    audit_evidence: Mapping[str, object],
    source: FrozenHip3MarkArchive,
    mark_evidence: Mapping[str, object],
    generator: Mapping[str, object],
) -> None:
    expected = {
        "sha256": audit_evidence.get("sha256"),
        "bytes": audit_evidence.get("bytes"),
    }
    if file_evidence(audit_path) != expected:
        raise ValueError("cohort audit changed during mark-stop analysis")
    source.require_unchanged(mark_evidence)
    if _generator_identity() != generator:
        raise ValueError("cohort mark-stop generator changed during analysis")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local audit and print only safe metadata."""
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
                "path_status": report["mark_stop_path"]["path_status"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
