#!/usr/bin/env python3
"""Publish immutable report-only technical acceptance for an exact v39 run."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.v39_poststart_acceptance import (
    build_v39_poststart_acceptance,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_CONFIG = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_OUTPUT_DIR = Path("data/logs/research/bidirectional_cohort")


def build_parser() -> argparse.ArgumentParser:
    """Build an execution-incapable acceptance command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--maximum-checkpoint-age-seconds", type=float, default=90.0)
    parser.add_argument("--maximum-pressure-age-seconds", type=float, default=30.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build and persist one immutable accepted or rejected technical report."""
    generated = datetime.now(UTC)
    output = args.out or _timestamped_output(generated)
    if output.exists():
        raise FileExistsError(f"v39 post-start acceptance already exists: {output}")
    checkpoint = _load_json(args.checkpoint, "checkpoint")
    config = load_multi_asset_live_config(args.config, mode="observe")
    report = build_v39_poststart_acceptance(
        checkpoint,
        config,
        now_utc=generated,
        maximum_checkpoint_age_seconds=args.maximum_checkpoint_age_seconds,
        maximum_pressure_age_seconds=args.maximum_pressure_age_seconds,
    )
    report["generated_at_utc"] = generated.isoformat()
    report["evidence"] = _evidence(args, output)
    write_atomic_json(output, report)
    return report


def exit_code(report: Mapping[str, object]) -> int:
    """Return zero only for an explicit technical acceptance."""
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("v39 acceptance result must be boolean")
    return 0 if accepted else 2


def command_summary(report: Mapping[str, object]) -> dict[str, object]:
    """Return bounded operator output without expanded metrics."""
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("v39 acceptance evidence must be an object")
    return {
        "accepted": report.get("accepted"),
        "decision": report.get("decision"),
        "reasons": report.get("reasons"),
        "out": evidence.get("output_path"),
        "execution_authority": "none",
    }


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"v39 post-start {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"v39 post-start {label} must be an object")
    return value


def _evidence(args: argparse.Namespace, output: Path) -> dict[str, object]:
    return {
        "checkpoint": _path_evidence(args.checkpoint),
        "config": _path_evidence(args.config),
        "output_path": str(output.resolve()),
    }


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _timestamped_output(generated: datetime) -> Path:
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    return _OUTPUT_DIR / f"v39_poststart_acceptance_{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    """Persist technical evidence without importing a venue execution client."""
    report = run(build_parser().parse_args(argv))
    print(json.dumps(command_summary(report), sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
