#!/usr/bin/env python3
"""Publish an immutable report-only V58 opportunity and co-trigger prefix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.v58_opportunity_cotrigger import (
    build_opportunity_cotrigger_report,
    contract_from_live_config,
)

_ROOT = Path(__file__).resolve().parents[1]
_GENERATORS = (
    "pyproject.toml",
    "uv.lock",
    "scripts/v58_opportunity_cotrigger.py",
    "src/hypervector/data/jsonl_prefix.py",
    "src/hypervector/live/multi_asset_live_config.py",
    "src/hypervector/research/v58_opportunity_cotrigger.py",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable opportunity-prefix parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--observer-ledger-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Read one exact prefix, recheck provenance, and publish once."""
    if args.out.exists():
        raise FileExistsError(f"immutable opportunity output exists: {args.out}")
    generators = _generator_identity()
    config_evidence = _path_evidence(args.config)
    base_config = load_multi_asset_live_config(args.config, mode="observe")
    config = base_config
    if args.observer_ledger_root is not None:
        config = with_observer_ledger_root(config, args.observer_ledger_root)
    rows, ledger_evidence = read_jsonl_prefix(args.ledger, "V58 observer ledger")
    report = build_opportunity_cotrigger_report(
        rows,
        contract=contract_from_live_config(config),
        run_id=args.run_id,
        source_evidence={
            "config": {
                **config_evidence,
                "base_profile_fingerprint": base_config.profile_fingerprint,
                "observer_profile_fingerprint": config.profile_fingerprint,
            },
            "ledger": ledger_evidence,
            "generators": generators,
        },
    )
    _require_unchanged(args, config_evidence, ledger_evidence, generators)
    write_immutable_json(args.out, report)
    return report


def _require_unchanged(
    args: argparse.Namespace,
    config: dict[str, object],
    ledger: dict[str, object],
    generators: dict[str, dict[str, object]],
) -> None:
    require_jsonl_prefix_unchanged(args.ledger, ledger, "V58 observer ledger")
    if _path_evidence(args.config) != config:
        raise RuntimeError("V58 config changed during opportunity evaluation")
    if _generator_identity() != generators:
        raise RuntimeError("V58 opportunity generator changed during evaluation")


def _path_evidence(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    return {"path": str(resolved), **file_evidence(resolved)}


def _generator_identity() -> dict[str, dict[str, object]]:
    return {relative: file_evidence(_ROOT / relative) for relative in _GENERATORS}


def main() -> int:
    """Run the report-only command and print a compact result."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(json.dumps({"out": str(args.out), "summary": report["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
