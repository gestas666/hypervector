#!/usr/bin/env python3
"""Publish the immutable V62 BRENTOIL profit-lock disposition."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.brentoil_profit_lock_decision import (
    evaluate_brentoil_profit_locks,
)

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-brentoil-profit-lock-future-only-preregistration-20260821-v4.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only publication parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build one source-bound BRENTOIL disposition without live authority."""
    checkpoint = _json(args.checkpoint, "checkpoint")
    preregistration = _json(args.preregistration, "preregistration")
    sources = {
        "checkpoint": _source_evidence(args.checkpoint),
        "preregistration": _source_evidence(args.preregistration),
    }
    evaluation = evaluate_brentoil_profit_locks(checkpoint, preregistration)
    _require_sources_unchanged(args, sources)
    return {
        "schema_version": 1,
        "mode": "v62_brentoil_profit_lock_decision_report_only",
        "hypothesis_id": preregistration.get("hypothesis_id"),
        "checkpoint_generated_at_utc": checkpoint.get("generated_at_utc"),
        "evaluation": evaluation,
        "sources": sources,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _json(path: Path, label: str) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"BRENTOIL {label} is missing: {path}")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping):
        raise ValueError(f"BRENTOIL {label} must be an object")
    return payload


def _source_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_sources_unchanged(
    args: argparse.Namespace,
    sources: Mapping[str, object],
) -> None:
    for name, path in (
        ("checkpoint", args.checkpoint),
        ("preregistration", args.preregistration),
    ):
        expected = sources.get(name)
        if not isinstance(expected, Mapping):
            raise ValueError(f"BRENTOIL source evidence is missing: {name}")
        actual = file_evidence(path)
        if actual.get("sha256") != expected.get("sha256") or actual.get(
            "bytes"
        ) != expected.get("bytes"):
            raise ValueError(f"BRENTOIL source changed during evaluation: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable decision artifact and print a bounded summary."""
    args = build_parser().parse_args(argv)
    report = run(args)
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "evaluation": report["evaluation"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
