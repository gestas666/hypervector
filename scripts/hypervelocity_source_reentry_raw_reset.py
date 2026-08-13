#!/usr/bin/env python3
"""Audit raw 5m reset-and-return alignment in creator same-side re-entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.source_reentry_raw_reset import raw_reset_reentry_evidence


def parser() -> argparse.ArgumentParser:
    """Build the immutable report-only audit interface."""
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--positions", type=Path, required=True)
    result.add_argument("--labels", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def run(args: argparse.Namespace) -> dict[str, object]:
    """Compute and publish one source-alignment report without execution authority."""
    positions = pd.read_csv(args.positions)
    labels = pd.read_parquet(args.labels)
    report: dict[str, object] = {
        "experiment": "source_same_side_raw_reset_alignment_v1",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "hypothesis": (
            "creator same-side re-entry follows a raw 5m reset-and-return "
            "that confirmed hysteresis does not expose"
        ),
        "evidence": {
            "positions": file_evidence(args.positions),
            "labels": file_evidence(args.labels),
        },
        "result": raw_reset_reentry_evidence(positions, labels),
    }
    write_immutable_json(args.out, report)
    return report


def main() -> int:
    """Run the audit and print only its compact result summary."""
    report = run(parser().parse_args())
    print(json.dumps(report["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
