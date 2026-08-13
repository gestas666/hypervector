#!/usr/bin/env python3
"""Publish immutable report-only provider-family concentration evidence."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_family_concentration import (
    build_family_concentration_report,
)
from hypervector.research.mu_hip3_archive_provenance import (
    require_unchanged_generator,
    source_tree_identity,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build explicit allocation, profile, equity, and output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allocation", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-equity-usd", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run_report(args: argparse.Namespace) -> dict[str, object]:
    """Build one exact-config concentration report without execution authority."""
    allocation = _load_json(args.allocation)
    config = load_multi_asset_live_config(args.config, mode="observe")
    _require_exact_roster(allocation, config.symbols)
    scopes = {
        provider.strategy_id: provider.execution_symbols
        for provider in config.providers
    }
    report = build_family_concentration_report(
        allocation,
        scopes,
        target_equity_usd=args.target_equity_usd,
    )
    project_root = Path(__file__).resolve().parents[1]
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "candidate_profile": {
                "profile_id": config.profile_id,
                "profile_fingerprint": config.profile_fingerprint,
            },
            "evidence": {
                "allocation": _path_evidence(args.allocation),
                "config": _path_evidence(args.config),
            },
            "generator_identity": source_tree_identity(
                project_root,
                Path(__file__).resolve(),
            ),
        }
    )
    return report


def _require_exact_roster(allocation: Record, symbols: tuple[str, ...]) -> None:
    assets = allocation.get("by_asset")
    if not isinstance(assets, Mapping):
        raise ValueError("allocation by_asset must be an object")
    allocated = frozenset(assets)
    configured = frozenset(symbols)
    if allocated != configured:
        raise ValueError(
            "allocation/config roster mismatch: "
            f"allocation={sorted(allocated)} config={sorted(configured)}"
        )


def _load_json(path: Path) -> Record:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"allocation is unreadable: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("allocation must be an object")
    return value


def _path_evidence(path: Path) -> dict[str, object]:
    evidence = file_evidence(path)
    evidence["path"] = str(path)
    return evidence


def main() -> int:
    """Publish one source-stable immutable diagnostic artifact."""
    args = build_parser().parse_args()
    report = run_report(args)
    identity = report.get("generator_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("generator identity is missing")
    require_unchanged_generator(
        dict(identity),
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve(),
    )
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "execution_authority": "none",
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
