#!/usr/bin/env python3
"""Continuously reconcile the exact live V58 BRENTOIL lifecycle report-only."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path
import sys
import time

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
)
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_brentoil_live_lifecycle_io import (
    bootstrap_v58_brentoil_preregistration,
    load_v58_brentoil_lifecycle_cycle,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

Report = dict[str, object]
CycleLoader = Callable[[argparse.Namespace, str, datetime], Report]
ReportWriter = Callable[[Path, Mapping[str, object]], None]
PathProvider = Callable[[], tuple[Path, ...]]
Sleep = Callable[[float], None]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_VENUE = Path("data/runtime/research/v58_current_venue_preflight_latest.json")
_LEDGER = Path("data/live/bidirectional_cohort/xyz:brentoil.jsonl")
_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_MANIFEST = Path(
    "data/backups/bidirectional_cohort/"
    "prestart_20260819T190754.078560Z_8a04636c9ff6/manifest.json"
)
_PREREGISTRATION = Path(
    "data/logs/research/v58_brentoil_live_lifecycle_preregistration_20260820_v1.json"
)
_STATUS = Path("data/runtime/research/v58_brentoil_live_lifecycle_latest.json")
_FINAL = Path(
    "data/logs/research/v58_brentoil_live_lifecycle_reconciliation_20260820_v1.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable lifecycle watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--venue", type=Path, default=_VENUE)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--prestart-manifest", type=Path, default=_MANIFEST)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--preregistration-sha256")
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--final", type=Path, default=_FINAL)
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def run_watcher(
    args: argparse.Namespace,
    *,
    cycle_loader: CycleLoader | None = None,
    atomic_writer: ReportWriter = write_atomic_json,
    immutable_writer: ReportWriter = write_immutable_json,
    generator_paths: PathProvider | None = None,
    sleep_fn: Sleep = time.sleep,
) -> int:
    """Publish open status until one exact immutable close is resolved."""
    _validate_runtime(args.interval_seconds, args.max_cycles)
    preregistration = _ensure_preregistration(args)
    source_paths = generator_paths or _generator_paths
    generators = _generator_identity(source_paths())
    loader = cycle_loader or _load_cycle
    cycles = 0
    while True:
        _require_unchanged_generators(generators)
        report = loader(args, str(preregistration["sha256"]), datetime.now(UTC))
        _require_cycle_contract(report)
        _require_unchanged_generators(generators)
        report["generator_identity"] = generators
        report["preregistration_identity"] = {
            "path": str(args.preregistration.resolve()),
            **preregistration,
        }
        state = report.get("state")
        if state == "resolved":
            immutable_writer(args.final, report)
            atomic_writer(args.status, report)
            return 0
        if state != "open_protected":
            raise ValueError("V58 BRENTOIL watcher received an unknown state")
        atomic_writer(args.status, report)
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.interval_seconds)


def _ensure_preregistration(args: argparse.Namespace) -> dict[str, object]:
    if args.preregistration.exists():
        if args.preregistration_sha256 is None:
            raise ValueError(
                "existing V58 BRENTOIL preregistration requires "
                "--preregistration-sha256"
            )
        evidence = file_evidence(args.preregistration)
        if evidence.get("sha256") != _sha256(args.preregistration_sha256):
            raise ValueError("V58 BRENTOIL preregistration hash differs")
        return evidence
    if args.preregistration_sha256 is not None:
        raise FileNotFoundError(
            f"V58 BRENTOIL preregistration is missing: {args.preregistration}"
        )
    preregistration = bootstrap_v58_brentoil_preregistration(
        _json(args.checkpoint, "checkpoint"),
        _json(args.venue, "venue preflight"),
        ledger_path=args.ledger,
        config_path=args.config,
        prestart_manifest_path=args.prestart_manifest,
        generated_at=datetime.now(UTC),
    )
    write_immutable_json(args.preregistration, preregistration)
    evidence = file_evidence(args.preregistration)
    print(
        json.dumps(
            {
                "event_type": "v58_brentoil_preregistration_created",
                "path": str(args.preregistration),
                "sha256": evidence["sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return evidence


def _load_cycle(
    args: argparse.Namespace, preregistration_sha256: str, generated_at: datetime
) -> Report:
    return load_v58_brentoil_lifecycle_cycle(
        args.preregistration,
        expected_preregistration_sha256=preregistration_sha256,
        checkpoint_path=args.checkpoint,
        venue_path=args.venue,
        ledger_path=args.ledger,
        generated_at=generated_at,
    )


def _require_cycle_contract(report: Mapping[str, object]) -> None:
    contract = report.get("contract")
    valid = (
        isinstance(contract, Mapping)
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("automatic_live_change") is False
        and contract.get("runtime_strategy_changed") is False
        and contract.get("portfolio_pnl_claimed") is False
        and contract.get("actual_orders_or_fills_claimed") is True
    )
    if not valid:
        raise ValueError("V58 BRENTOIL watcher report-only contract differs")


def _generator_identity(paths: Sequence[Path]) -> list[dict[str, object]]:
    return [{"path": str(path.resolve()), **file_evidence(path)} for path in paths]


def _require_unchanged_generators(rows: Sequence[Mapping[str, object]]) -> None:
    for row in rows:
        require_unchanged_file(Path(str(row["path"])), row)


def _generator_paths() -> tuple[Path, ...]:
    project = Path(__file__).resolve().parents[1]
    return tuple(
        (project / path).resolve()
        for path in (
            "scripts/v58_brentoil_live_lifecycle_watch.py",
            "src/hypervector/research/v58_brentoil_live_lifecycle.py",
            "src/hypervector/research/v58_brentoil_live_contracts.py",
            "src/hypervector/research/v58_brentoil_live_lifecycle_io.py",
            "src/hypervector/research/v58_brentoil_live_venue.py",
            "src/hypervector/research/v58_live_close_ledger.py",
            "src/hypervector/research/cohort_lifecycle_evidence.py",
            "src/hypervector/research/cohort_live_audit_values.py",
            "src/hypervector/data/jsonl_prefix.py",
            "src/hypervector/data/oxa_storage.py",
            "src/hypervector/research/checkpoint_storage.py",
            "src/hypervector/research/hip3_development_provenance.py",
            "src/hypervector/runtime_lock.py",
            "pyproject.toml",
            "uv.lock",
        )
    )


def _json(path: Path, label: str) -> Mapping[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 BRENTOIL {label} must be an object")
    return value


def _validate_runtime(interval_seconds: object, max_cycles: object) -> None:
    valid_interval = (
        not isinstance(interval_seconds, bool)
        and isinstance(interval_seconds, (int, float))
        and isfinite(float(interval_seconds))
        and float(interval_seconds) > 0.0
    )
    if not valid_interval:
        raise ValueError("V58 BRENTOIL interval must be finite and positive")
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 0
    ):
        raise ValueError("V58 BRENTOIL max cycles must be nonnegative")


def _sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("V58 BRENTOIL preregistration SHA-256 is invalid")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("V58 BRENTOIL preregistration SHA-256 is invalid")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton authority-none lifecycle watcher."""
    args = build_parser().parse_args(argv)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 BRENTOIL lifecycle watcher failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
