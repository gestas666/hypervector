#!/usr/bin/env python3
"""Publish the immutable normalized comparison for the first V58 ETH close."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.v58_eth_exit_comparison import (
    build_v58_eth_exit_comparison,
)

_CLOSE = Path(
    "data/logs/research/v58_eth_first_live_close_reconciliation_20260820_v1.json"
)
_DURATION = Path(
    "data/logs/research/v58_eth_duration_checkpoint_20260820T045524Z_v1.json"
)
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-eth-first-live-exit-duration-comparison-preregistration-20260820-v1.json"
)
_PREREGISTRATION_SHA256 = (
    "5061e33d153dc1e54a4e23d9ba8d69f604abc78c8415fc095f3b6a4e96346e43"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only comparison parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--close", type=Path, default=_CLOSE)
    parser.add_argument("--duration", type=Path, default=_DURATION)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--preregistration-sha256", default=_PREREGISTRATION_SHA256)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Build and immutably publish one source-bound authority-none report."""
    generators = _generator_identity()
    preregistration, preregistration_evidence = _load_json(
        args.preregistration, "comparison_preregistration"
    )
    close, close_evidence = _load_json(args.close, "live_close_reconciliation")
    duration, duration_evidence = _load_json(args.duration, "duration_checkpoint")
    _validate_preregistration(
        preregistration,
        preregistration_evidence,
        args.preregistration_sha256,
        args.duration,
        close,
    )
    report = build_v58_eth_exit_comparison(close, duration)
    _require_unchanged(args.preregistration, preregistration_evidence)
    _require_unchanged(args.close, close_evidence)
    _require_unchanged(args.duration, duration_evidence)
    _require_unchanged_generators(generators)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["source_evidence"] = [
        preregistration_evidence,
        close_evidence,
        duration_evidence,
    ]
    report["generator_identity"] = generators
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable comparison publisher."""
    args = build_parser().parse_args(argv)
    try:
        report = publish_report(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"V58 ETH exit comparison failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "out": str(args.out),
                "mode": report["mode"],
                "execution_authority": report["contract"]["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_json(
    path: Path, label: str
) -> tuple[Mapping[str, object], dict[str, object]]:
    evidence = {"label": label, "path": str(path), **file_evidence(path)}
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping):
        raise ValueError(f"V58 ETH exit comparison {label} must be a mapping")
    return payload, evidence


def _require_unchanged(path: Path, expected: Mapping[str, object]) -> None:
    require_unchanged_file(path, expected)


def _validate_preregistration(
    payload: Mapping[str, object],
    evidence: Mapping[str, object],
    expected_sha256: str,
    duration_path: Path,
    close: Mapping[str, object],
) -> None:
    if evidence.get("sha256") != expected_sha256:
        raise ValueError("V58 ETH exit comparison preregistration hash differs")
    expected = {
        "scope": "v58_eth_first_live_exit_duration_comparison_preregistration",
        "hypothesis_id": "v58_eth_first_live_exit_duration_comparison_v1",
        "status": "being_tested",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH exit comparison preregistration differs")
    prereg_identity = payload.get("frozen_identity")
    close_identity = close.get("frozen_identity")
    if not isinstance(prereg_identity, Mapping) or prereg_identity != close_identity:
        raise ValueError("V58 ETH exit comparison preregistration identity differs")
    if payload.get("contract") != close.get("contract"):
        raise ValueError("V58 ETH exit comparison preregistration contract differs")
    duration = _nested_mapping(payload, "frozen_inputs", "duration_checkpoint")
    observed = file_evidence(duration_path)
    if duration.get("path") != str(duration_path):
        raise ValueError("V58 ETH exit comparison duration path differs")
    if any(duration.get(key) != observed[key] for key in ("bytes", "sha256")):
        raise ValueError("V58 ETH exit comparison duration evidence differs")


def _nested_mapping(
    payload: Mapping[str, object], outer: str, inner: str
) -> Mapping[str, object]:
    first = payload.get(outer)
    if not isinstance(first, Mapping):
        raise ValueError(f"V58 ETH exit comparison {outer} must be a mapping")
    second = first.get(inner)
    if not isinstance(second, Mapping):
        raise ValueError(f"V58 ETH exit comparison {inner} must be a mapping")
    return second


def _generator_identity() -> list[dict[str, object]]:
    return [
        {"path": str(path.resolve()), **file_evidence(path)}
        for path in _generator_paths()
    ]


def _require_unchanged_generators(expected: Sequence[Mapping[str, object]]) -> None:
    for row in expected:
        require_unchanged_file(Path(str(row["path"])), row)


def _generator_paths() -> tuple[Path, ...]:
    project = Path(__file__).resolve().parents[1]
    return (
        Path(__file__).resolve(),
        project / "src/hypervector/research/v58_eth_exit_comparison.py",
        project / "src/hypervector/data/oxa_storage.py",
        project / "src/hypervector/research/hip3_development_provenance.py",
        project / "pyproject.toml",
        project / "uv.lock",
    )


if __name__ == "__main__":
    raise SystemExit(main())
