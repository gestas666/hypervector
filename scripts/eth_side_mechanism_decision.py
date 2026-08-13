#!/usr/bin/env python3
"""Publish the exact report-only ETH side-mechanism decision."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.eth_side_mechanism_decision import (
    build_eth_side_mechanism_decision,
)

_ATTRIBUTION = Path(
    "data/logs/research/bidirectional_cohort/"
    "eth_pullback_mechanism_attribution_exact_v4_20260809T123838Z.json"
)
_DURATION = Path(
    "data/logs/research/bidirectional_cohort/"
    "eth_pullback_mechanism_duration_20260809T203358Z.json"
)
_STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
_OUTPUT = Path(
    f"data/logs/research/bidirectional_cohort/eth_side_mechanism_decision_{_STAMP}.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attribution", type=Path, default=_ATTRIBUTION)
    parser.add_argument("--duration", type=Path, default=_DURATION)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Validate both frozen sources and publish one immutable decision."""
    attribution = _read_object(args.attribution, "ETH attribution")
    duration = _read_object(args.duration, "ETH duration")
    report = build_eth_side_mechanism_decision(attribution, duration)
    report["source"] = {
        "attribution": {
            "path": str(args.attribution.resolve()),
            **file_evidence(args.attribution),
        },
        "duration": {
            "path": str(args.duration.resolve()),
            **file_evidence(args.duration),
        },
    }
    write_immutable_json(args.out, report)
    return report


def _read_object(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def main() -> int:
    """Run the decision and print a bounded non-authoritative summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    assessment = report.get("assessment")
    if not isinstance(assessment, dict):
        raise RuntimeError("ETH side decision assessment is unavailable")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.out.resolve()),
                "decision": report["decision"],
                "stable_sides": assessment["stable_side_arms"],
                "stable_side_relations": assessment["stable_side_relation_arms"],
                "execution_authority": "none",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
