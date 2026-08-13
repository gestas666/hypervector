#!/usr/bin/env python3
"""Audit cross-block robustness for one frozen maker-risk candidate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.maker_risk_robustness import summarize_candidate_blocks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--block", action="append", type=Path, required=True)
    parser.add_argument("--holdout", action="append", type=Path, default=[])
    parser.add_argument("--candidate", default="alloc70_lev30")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _experiment_contract(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema": "hypervelocity_maker_risk_robustness_v1",
        "candidate": str(args.candidate),
        "report_only": True,
        "runtime_strategy_changed": False,
        "selection_is_promotion": False,
        "portfolio_paths_stitched_across_gaps": False,
    }


def _load_block(path: Path) -> Mapping[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"maker risk block must be a JSON object: {path}")
    return value


def _evidence(paths: Sequence[Path]) -> list[dict[str, object]]:
    return [
        {
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]


def _report(args: argparse.Namespace) -> dict[str, object]:
    block_paths = list(args.block)
    holdout_paths = list(args.holdout)
    blocks = [_load_block(path) for path in block_paths]
    holdouts = [_load_block(path) for path in holdout_paths]
    candidate = str(args.candidate)
    return {
        **_experiment_contract(args),
        "development_evidence": _evidence(block_paths),
        "holdout_evidence": _evidence(holdout_paths),
        "development": summarize_candidate_blocks(blocks, candidate),
        "holdout": (
            summarize_candidate_blocks(holdouts, candidate) if holdouts else None
        ),
        "combined_sensitivity": summarize_candidate_blocks(
            [*blocks, *holdouts], candidate
        ),
        "limitations": [
            "Public trade-through cannot identify private maker queue rank.",
            (
                "Wilson bounds assume approximately independent stationary binary "
                "outcomes; regime clustering can make them optimistic."
            ),
            "Wilson bounds measure sampling uncertainty, not selection bias.",
            "Leave-one-block-out results do not create a continuous portfolio path.",
            "Only a new continuous shadow window is forward evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write one immutable report-only robustness artifact."""
    args = _parser().parse_args(argv)
    write_immutable_json(args.out, _report(args))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
