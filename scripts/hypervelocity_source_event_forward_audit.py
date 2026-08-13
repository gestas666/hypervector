#!/usr/bin/env python3
"""Publish side-aware paths for every live source-follow directional onset."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.source_follow_live_config import (
    SourceFollowLiveConfig,
    load_source_follow_live_config,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.source_follow_event_forward import (
    SourceEventMeasurementContract,
    audit_source_event_forward_paths,
    extract_source_event_decisions,
    extract_source_event_measurement_contract,
)

_DEFAULT_HORIZONS = (5, 15, 30, 60)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--horizon-minutes", type=int, action="append")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _report(args: argparse.Namespace) -> dict[str, object]:
    config = load_source_follow_live_config(args.config)
    with snapshot_decision_ledger(args.decisions) as (rows, decisions_evidence):
        contract = extract_source_event_measurement_contract(
            rows,
            run_id=args.run_id,
        )
        measurement_match = _measurement_matches(config, contract)
        if not measurement_match:
            raise ValueError("live measurement contract differs from current config")
        events = extract_source_event_decisions(rows, run_id=args.run_id)
        report = audit_source_event_forward_paths(
            args.database,
            events,
            symbol=contract.symbol,
            target_price_fraction=contract.target_price_fraction,
            minimum_range_bps=contract.minimum_range_bps,
            maximum_range_bps=contract.maximum_range_bps,
            horizons_minutes=tuple(args.horizon_minutes or _DEFAULT_HORIZONS),
        )
    report.update(
        {
            "run_id": args.run_id,
            "profile_id": config.profile_id,
            "profile_fingerprint": config.profile_fingerprint,
            "ledger_profile_fingerprint": contract.profile_fingerprint,
            "profile_fingerprint_match": (
                contract.profile_fingerprint == config.profile_fingerprint
            ),
            "measurement_contract_matches_current_config": measurement_match,
            "evidence": {
                "config": file_evidence(args.config),
                "decisions": decisions_evidence,
                "database": file_evidence(args.database),
            },
        }
    )
    return report


def _measurement_matches(
    config: SourceFollowLiveConfig,
    contract: SourceEventMeasurementContract,
) -> bool:
    profile = config.profile
    current_target = config.target_margin_pct / config.leverage / 100.0
    return (
        contract.profile_id == config.profile_id
        and contract.symbol == config.symbol
        and contract.minimum_range_bps == profile.minimum_range_bps
        and contract.maximum_range_bps == profile.maximum_range_bps
        and math.isclose(
            contract.target_price_fraction,
            current_target,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
    )


def _publish(args: argparse.Namespace) -> dict[str, object]:
    if args.out.exists():
        raise FileExistsError(f"immutable source-event audit exists: {args.out}")
    report = _report(args)
    write_immutable_json(args.out, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Publish immutable report-only onset evidence without execution authority."""
    args = _parser().parse_args(argv)
    report = _publish(args)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "run_id": report["run_id"],
                "event_rows": report["event_rows"],
                "report_only": report["report_only"],
                "execution_authority": report["execution_authority"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
