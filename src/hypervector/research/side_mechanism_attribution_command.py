"""Shared command boundary for immutable side-mechanism attribution."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json

AttributionBuilder = Callable[[Path, Path], dict[str, object]]


def attribution_parser(
    description: str,
    *,
    source: Path,
    trades: Path,
    output: Path,
) -> argparse.ArgumentParser:
    """Build the common immutable, report-only attribution parser."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source", type=Path, default=source)
    parser.add_argument("--trades", type=Path, default=trades)
    parser.add_argument("--out", type=Path, default=output)
    return parser


def publish_attribution(
    args: argparse.Namespace,
    builder: AttributionBuilder,
) -> dict[str, object]:
    """Build and atomically publish one immutable attribution artifact."""
    report = builder(args.source, args.trades)
    write_immutable_json(args.out, report)
    return report


def print_attribution_summary(
    args: argparse.Namespace,
    report: dict[str, object],
) -> None:
    """Print a bounded summary that cannot imply execution authority."""
    assessment = report["assessment"]
    if not isinstance(assessment, dict):
        raise ValueError("attribution assessment must be an object")
    summary = {
        "ok": True,
        "output": str(args.out.resolve()),
        "decision": report["decision"],
        "stable_arms": assessment["stable_side_timing_arms"],
        "execution_authority": "none",
    }
    print(json.dumps(summary, indent=2))
