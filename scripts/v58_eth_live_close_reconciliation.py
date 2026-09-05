#!/usr/bin/env python3
"""Publish immutable source-bound evidence for the first V58 ETH live close."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_eth_live_close_reconciliation_io import (
    load_v58_eth_live_close_reconciliation,
)

_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-eth-first-live-close-reconciliation-preregistration-20260820-v1.json"
)
_PREREGISTRATION_SHA256 = (
    "d11a0540bb03632551435feee152ba23c05643faf4033318412589f62d70fb68"
)
_CONTINUOUS = Path("data/runtime/research/v58_continuous_improvement_latest.json")
_VENUE = Path("data/runtime/research/v58_current_venue_preflight_latest.json")
_OBSERVER = Path("data/runtime/research/v58_eth_pullback_first_lifecycle_latest.json")
_OBSERVER_PROVENANCE = Path(
    "docs/research-journal/"
    "v58-observer-window-provenance-reclassification-20260820-v1.json"
)
_OBSERVER_PROVENANCE_SHA256 = (
    "83b1c9f1891e62f02e9fac67275bb1cd59f48f0a81ba6bc72c5939bb2563caa7"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only publisher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--preregistration-sha256", default=_PREREGISTRATION_SHA256)
    parser.add_argument("--continuous", type=Path, default=_CONTINUOUS)
    parser.add_argument("--venue", type=Path, default=_VENUE)
    parser.add_argument("--observer-status", type=Path, default=_OBSERVER)
    parser.add_argument(
        "--observer-provenance", type=Path, default=_OBSERVER_PROVENANCE
    )
    parser.add_argument(
        "--observer-provenance-sha256", default=_OBSERVER_PROVENANCE_SHA256
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Build and immutably publish one authority-none close report."""
    generators = _generator_identity()
    report = load_v58_eth_live_close_reconciliation(
        args.preregistration,
        expected_preregistration_sha256=args.preregistration_sha256,
        continuous_path=args.continuous,
        venue_path=args.venue,
        observer_status_path=args.observer_status,
        observer_provenance_path=args.observer_provenance,
        expected_observer_provenance_sha256=args.observer_provenance_sha256,
        generated_at=datetime.now(UTC),
    )
    _require_unchanged_generators(generators)
    report["generator_identity"] = generators
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable report-only publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 ETH live-close reconciliation failed: {exc}", file=sys.stderr)
        return 2
    output = {
        "out": str(args.out),
        "mode": report.get("mode"),
        "execution_authority": report.get("contract", {}).get("execution_authority"),
    }
    print(json.dumps(output, sort_keys=True))
    return 0


def _generator_identity() -> list[dict[str, object]]:
    return [
        {"path": str(path.resolve()), **file_evidence(path)}
        for path in _generator_paths()
    ]


def _require_unchanged_generators(expected: list[dict[str, object]]) -> None:
    for row in expected:
        require_unchanged_file(Path(str(row["path"])), row)


def _generator_paths() -> tuple[Path, ...]:
    project = Path(__file__).resolve().parents[1]
    return (
        Path(__file__).resolve(),
        project / "src/hypervector/research/v58_eth_live_close_reconciliation.py",
        project / "src/hypervector/research/v58_eth_live_close_ledger.py",
        project / "src/hypervector/research/v58_eth_live_close_reconciliation_io.py",
        project / "src/hypervector/research/cohort_lifecycle_evidence.py",
        project / "src/hypervector/research/cohort_live_audit_values.py",
        project / "src/hypervector/data/jsonl_prefix.py",
        project / "src/hypervector/data/oxa_storage.py",
        project / "src/hypervector/research/hip3_development_provenance.py",
        project / "pyproject.toml",
        project / "uv.lock",
    )


if __name__ == "__main__":
    raise SystemExit(main())
