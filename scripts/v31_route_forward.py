#!/usr/bin/env python3
"""Publish bounded report-only telemetry for the inactive or active v31 prune."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v31_route_forward import (
    build_v31_route_forward_snapshot,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v1.json")
_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_v31_route_forward.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable route-forward tracker parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--source-config", type=Path, default=_SOURCE)
    parser.add_argument("--candidate-config", type=Path, default=_CANDIDATE)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument(
        "--immutable",
        action="store_true",
        help="refuse an existing output instead of replacing the bounded snapshot",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Validate inputs and atomically publish one route-forward snapshot."""
    if args.immutable and args.out.exists():
        raise FileExistsError(f"v31 route-forward output already exists: {args.out}")
    checkpoint = _load_json(args.checkpoint, "checkpoint")
    journal = _load_json(args.journal, "journal")
    report = build_v31_route_forward_snapshot(
        checkpoint,
        journal,
        args.source_config,
        args.candidate_config,
    )
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["evidence"] = {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
        "source_config": _path_evidence(args.source_config),
        "candidate_config": _path_evidence(args.candidate_config),
    }
    write_atomic_json(args.out, report)
    return report


def command_summary(report: Mapping[str, object]) -> dict[str, object]:
    """Return bounded operator telemetry without route payload expansion."""
    assessment = report.get("assessment")
    if not isinstance(assessment, Mapping):
        raise ValueError("v31 route-forward assessment must be an object")
    return {
        "phase": report.get("phase"),
        "tracking_state": report.get("tracking_state"),
        "current_open_positions": assessment.get("current_open_positions"),
        "removed_route_eligible_signals": assessment.get(
            "removed_route_eligible_signals"
        ),
        "execution_authority": "none",
    }


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"v31 route-forward {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"v31 route-forward {label} must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bounded tracker without importing a venue order client."""
    args = build_parser().parse_args(argv)
    report = run(args)
    print(json.dumps({"ok": True, "out": str(args.out), **command_summary(report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
