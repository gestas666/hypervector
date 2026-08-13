#!/usr/bin/env python3
"""Continuously publish exact-profile, report-only v39 forward evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v39_forward_evidence import build_v39_forward_evidence

Record = Mapping[str, object]
SleepFn = Callable[[float], None]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_v39_forward_evidence.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable v39 evidence monitor parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def refresh(args: argparse.Namespace) -> dict[str, object]:
    """Build and atomically publish one exact v39 evidence snapshot."""
    _validate_paths(args)
    checkpoint_raw = args.checkpoint.read_bytes()
    config_raw = args.config.read_bytes()
    checkpoint = _mapping(json.loads(checkpoint_raw), "v39 checkpoint")
    config = _load_bound_config(config_raw)
    generated = datetime.now(UTC)
    report = build_v39_forward_evidence(checkpoint, config, observed_at=generated)
    report.update(
        {
            "generated_at_utc": generated.isoformat(),
            "material_state_sha256": _digest(report),
            "evidence": {
                "checkpoint": _file_record(args.checkpoint, checkpoint_raw),
                "config": _file_record(args.config, config_raw),
            },
        }
    )
    write_atomic_json(args.out, report)
    return report


def run_monitor(args: argparse.Namespace, *, sleep_fn: SleepFn = time.sleep) -> int:
    """Refresh until stopped while preserving the last valid snapshot."""
    _validate_loop_args(args)
    completed = 0
    while True:
        try:
            report = refresh(args)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            _emit_failure(exc)
            if args.once:
                return 2
        else:
            completed += 1
            _emit_success(report)
            if args.once or (args.max_cycles and completed >= args.max_cycles):
                return 0
        sleep_fn(args.interval_seconds)


def _validate_loop_args(args: argparse.Namespace) -> None:
    _validate_paths(args)
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0.0:
        raise ValueError("v39 evidence monitor interval must be finite and positive")
    if args.max_cycles < 0:
        raise ValueError("v39 evidence monitor max cycles cannot be negative")


def _validate_paths(args: argparse.Namespace) -> None:
    output = args.out.resolve()
    if output in {args.checkpoint.resolve(), args.config.resolve()}:
        raise ValueError("v39 evidence output must differ from all evidence inputs")


def _load_bound_config(raw: bytes) -> object:
    with TemporaryDirectory(prefix="hypervector-v39-config-") as directory:
        path = Path(directory) / "bound-config.toml"
        path.write_bytes(raw)
        return load_multi_asset_live_config(
            path,
            mode="observe",
            enabled=False,
            accepts_live_risk=False,
        )


def _file_record(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _emit_success(report: Record) -> None:
    summary = _mapping(report.get("summary"), "v39 evidence summary")
    source = _mapping(report.get("source"), "v39 evidence source")
    print(
        json.dumps(
            {
                "event": "v39_forward_evidence",
                "state": "published",
                "run_id": source.get("run_id"),
                "closed_trades": summary.get("closed_trades"),
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _emit_failure(exc: Exception) -> None:
    print(
        json.dumps(
            {
                "event": "v39_forward_evidence",
                "state": "unavailable",
                "technical_issue": f"{type(exc).__name__}: {exc}",
                "execution_authority": "none",
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _digest(value: Record) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the exact v39 report-only evidence monitor."""
    return run_monitor(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
