#!/usr/bin/env python3
"""Publish an immutable report-only retest replay from one live-ledger snapshot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.hype_breakout_retest_replay import (
    build_hype_breakout_retest_replay,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay breakout retests without execution authority."
    )
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--window-bars", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Snapshot, replay, and publish one immutable causal timing report."""
    args = _parser().parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"immutable retest replay already exists: {args.out}")
    with snapshot_decision_ledger(
        args.decisions,
        allow_incomplete_tail=True,
    ) as (rows, evidence):
        report = build_hype_breakout_retest_replay(
            rows,
            run_id=args.run_id,
            window_bars=args.window_bars,
        )
    report["evidence"] = {"path": str(args.decisions), **evidence}
    write_immutable_json(args.out, report)
    print(
        json.dumps(
            {
                "execution_authority": "none",
                "out": str(args.out),
                "report_only": True,
                "run_id": args.run_id,
                "summary": report["summary"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
