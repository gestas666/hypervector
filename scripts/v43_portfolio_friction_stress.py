#!/usr/bin/env python3
"""Publish immutable full-roster v43 friction and stop-wave stress."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import math
from pathlib import Path
import sys

import duckdb

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)
from hypervector.research.cohort_execution_friction import collect_execution_friction

Record = Mapping[str, object]
_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_DATABASE = Path("data/research/market.duckdb")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v43_portfolio_friction_stress_20260811_v2.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build a mutation-incapable report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=_PROFILE)
    parser.add_argument("--venue-stress", type=Path, default=_VENUE)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--schema-version", default="v43_portfolio_friction_stress_v1")
    parser.add_argument(
        "--account-values-usd", type=float, nargs="+", default=[500.0, 5_000.0]
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Build, reconcile, and atomically publish one immutable report."""
    config = load_multi_asset_live_config(args.profile, mode="observe")
    friction, evidence = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    report = build_v43_portfolio_friction_stress(
        args.profile,
        venue_stress_path=args.venue_stress,
        execution_friction=friction,
        account_values_usd=args.account_values_usd,
        schema_version=args.schema_version,
    )
    final_friction, final_evidence = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    if (friction, evidence) != (final_friction, final_evidence):
        raise RuntimeError("v43 execution evidence changed during evaluation")
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "execution_friction_evidence": friction,
            "source_execution_evidence": evidence,
            "inputs": {
                "profile": _file_identity(args.profile),
                "venue_stress": _file_identity(args.venue_stress),
                "checkpoint": _file_identity(args.checkpoint),
            },
        }
    )
    write_immutable_json(args.output, report)
    return 0


def _file_identity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    """Return a bounded report failure without exposing live authority."""
    try:
        return run(build_parser().parse_args(argv))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
        duckdb.Error,
    ) as exc:
        print(f"v43 portfolio friction stress failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
