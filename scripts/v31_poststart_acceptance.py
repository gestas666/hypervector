#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for an exact v31 run."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v31_poststart_acceptance import (
    build_v31_poststart_acceptance,
)
from hypervector.research.v31_route_forward import (
    build_v31_route_forward_snapshot,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v1.json")
_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable immutable verifier parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--journal", type=Path, default=_JOURNAL)
    parser.add_argument("--source-config", type=Path, default=_SOURCE)
    parser.add_argument("--candidate-config", type=Path, default=_CANDIDATE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build and persist one immutable accepted or rejected report."""
    generated = datetime.now(UTC)
    output = args.out or _timestamped_output(generated)
    if output.exists():
        raise FileExistsError(
            f"v31 post-start acceptance output already exists: {output}"
        )
    checkpoint = _load_json(args.checkpoint, "checkpoint")
    journal = _load_json(args.journal, "journal")
    route_snapshot = build_v31_route_forward_snapshot(
        checkpoint,
        journal,
        args.source_config,
        args.candidate_config,
    )
    report = build_v31_poststart_acceptance(
        checkpoint,
        route_snapshot,
        maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
    )
    report["generated_at_utc"] = generated.isoformat()
    report["evidence"] = _evidence(args, output)
    write_atomic_json(output, report)
    return report


def exit_code(report: Mapping[str, object]) -> int:
    """Return zero only for a persisted technical acceptance."""
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("v31 post-start report accepted state must be boolean")
    return 0 if accepted else 2


def command_summary(report: Mapping[str, object]) -> dict[str, object]:
    """Return bounded operator output without metric expansion."""
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("v31 post-start evidence must be an object")
    return {
        "accepted": report.get("accepted"),
        "decision": report.get("decision"),
        "reasons": report.get("reasons"),
        "out": evidence.get("output_path"),
        "execution_authority": "none",
    }


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"v31 post-start {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"v31 post-start {label} must be an object")
    return value


def _evidence(args: argparse.Namespace, output: Path) -> dict[str, object]:
    return {
        "checkpoint": _path_evidence(args.checkpoint),
        "journal": _path_evidence(args.journal),
        "source_config": _path_evidence(args.source_config),
        "candidate_config": _path_evidence(args.candidate_config),
        "output_path": str(output.resolve()),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _timestamped_output(generated: datetime) -> Path:
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return _OUTPUT_DIR / f"v31_poststart_acceptance_{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Persist acceptance evidence without importing a venue order client."""
    report = run(build_parser().parse_args(argv))
    print(json.dumps(command_summary(report), sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
