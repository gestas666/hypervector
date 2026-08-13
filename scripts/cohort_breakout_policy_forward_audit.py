#!/usr/bin/env python3
"""Publish policy-parity forward evidence for the staged all-asset breakout."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_breakout_policy_contract import (
    breakout_policy_forward_spec,
)
from hypervector.research.cohort_breakout_policy_forward import (
    build_breakout_policy_forward_report,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_DEFAULT_DECISIONS = Path("data/live/bidirectional_cohort/decisions.jsonl")
_DEFAULT_SOURCE = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_DEFAULT_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only audit command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, default=_DEFAULT_DECISIONS)
    parser.add_argument("--source-config", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--candidate-config", type=Path, default=_DEFAULT_CANDIDATE)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def publish(args: argparse.Namespace) -> dict[str, object]:
    """Snapshot the active ledger and immutably publish policy evidence."""
    if args.out.exists():
        raise FileExistsError(f"breakout policy audit output exists: {args.out}")
    source = load_multi_asset_live_config(args.source_config, mode="observe")
    candidate = load_multi_asset_live_config(args.candidate_config, mode="observe")
    with snapshot_decision_ledger(
        args.decisions,
        allow_incomplete_tail=True,
    ) as (records, ledger_evidence):
        spec = breakout_policy_forward_spec(
            source,
            candidate,
            records,
            run_id=args.run_id,
        )
        report = build_breakout_policy_forward_report(records, spec=spec)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["evidence"] = {
        "ledger": {"path": str(args.decisions), **ledger_evidence},
        "source_config": {
            "path": str(args.source_config),
            **file_evidence(args.source_config),
        },
        "candidate_config": {
            "path": str(args.candidate_config),
            **file_evidence(args.candidate_config),
        },
    }
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish one audit without constructing any execution client."""
    args = build_parser().parse_args(argv)
    report = publish(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "summary": report["summary"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
