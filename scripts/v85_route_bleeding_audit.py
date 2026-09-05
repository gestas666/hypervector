#!/usr/bin/env python3
"""Publish one immutable, report-only V85 route bleeding audit."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.v85_route_bleeding_audit import (
    build_route_bleeding_audit,
    load_frozen_jsonl_prefix,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the authority-free immutable audit command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
    """Rebuild the frozen audit and publish it exactly once."""
    if args.out.exists():
        raise FileExistsError(f"immutable route audit output exists: {args.out}")
    preregistration = _load_object(args.preregistration)
    cohort_evidence = _object(
        preregistration.get("frozen_cohort_ledger_prefix"), "cohort prefix"
    )
    cohort, cohort_facts = load_frozen_jsonl_prefix(cohort_evidence)
    asset_evidence = _object(
        preregistration.get("frozen_asset_ledger_prefixes"), "asset prefixes"
    )
    assets: dict[str, list[dict[str, object]]] = {}
    asset_facts: dict[str, dict[str, object]] = {}
    for symbol, evidence in asset_evidence.items():
        rows, facts = load_frozen_jsonl_prefix(_object(evidence, f"{symbol} prefix"))
        assets[symbol] = rows
        asset_facts[symbol] = facts
    identity = _object(
        preregistration.get("frozen_runtime_identity"), "runtime identity"
    )
    run_id = _text(identity.get("run_id"), "run id")
    audit = audit_multi_asset_live_run(
        cohort,
        assets,
        all_time_asset_records=assets,
        run_id=run_id,
    )
    report = build_route_bleeding_audit(audit, preregistration)
    report["evidence"] = {
        "frozen_prefixes_verified": True,
        "cohort": cohort_facts,
        "assets": asset_facts,
    }
    write_immutable_json(args.out, report)
    return report, args.out


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the immutable route bleeding audit command."""
    _, output = publish(build_parser().parse_args(argv))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
