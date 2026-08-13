#!/usr/bin/env python3
"""Continuously journal the v49 SOL Range signal under its exact policy."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path
import sys
import time

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_config_bound_policy_forward import (
    ConfigBoundPolicyForwardBinding,
    build_config_bound_policy_forward_report,
)
from hypervector.research.cohort_eligible_exact_depth_forward import (
    build_eligible_exact_depth_forward_report,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.research.cohort_forward_paths import MINUTE_MS, build_candle_index
from hypervector.research.cohort_live_audit_values import timestamp
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
)
from hypervector.research.cohort_policy_forward_profit_lock import (
    build_policy_forward_profit_lock_report,
)
from hypervector.research.cohort_signal_candidates import evaluation_candidates
from hypervector.research.cohort_trade_reflection_index import (
    build_reflection_evidence_index,
)
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]
PublishFn = Callable[[argparse.Namespace], dict[str, object]]
_CONFIG = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_LEDGER_ROOT = Path("data/observe/v49_candidate_shadow")
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json"
)
_OUTPUT = Path("data/runtime/research/v49_range_onset_sol_policy_forward_latest.json")
_STRATEGY = "range_onset_bidirectional_v1"
_CANDIDATE = "range_onset_sol_v49_config_bound_forward_v1"
_MAXIMUM_BOOK_DELAY_MS = 60_000
_BPS_PER_ROUND_TRIP_RATE = 20_000.0


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable rolling policy monitor CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger-root", type=Path, default=_LEDGER_ROOT)
    parser.add_argument("--stress", type=Path, default=_STRESS)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    return parser


def publish_policy_checkpoint(args: argparse.Namespace) -> dict[str, object]:
    """Publish one stable, source-bound, report-only policy lifecycle snapshot."""
    config_evidence = file_evidence(args.config)
    stress_evidence = file_evidence(args.stress)
    base = load_multi_asset_live_config(args.config, mode="observe")
    runtime = with_observer_ledger_root(base, args.ledger_root)
    stress = _json_object(args.stress)
    with snapshot_decision_ledger(
        runtime.cohort_ledger,
        allow_incomplete_tail=True,
    ) as (records, ledger_evidence):
        selected, identities = select_compatible_report_only_observer_runs(
            records, args.run_id
        )
        funding, funding_status = _funding_evidence(selected, args.run_id)
        report = build_config_bound_policy_forward_report(
            selected,
            base_config=base,
            runtime_config=runtime,
            stress_report=stress,
            binding=_binding(),
            run_id=args.run_id,
            funding_evidence=funding,
        )
        exact = _exact_depth_lifecycle(selected, report, funding)
        report["exact_visible_depth_lifecycle"] = exact
        report["profit_lock_challenger"] = _profit_lock_lifecycle(
            selected, report, exact
        )
    require_unchanged_file(args.config, config_evidence)
    require_unchanged_file(args.stress, stress_evidence)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["source_evidence"] = {
        "ledger": {"path": str(runtime.cohort_ledger), **ledger_evidence},
        "config": {"path": str(args.config), **config_evidence},
        "stress": {"path": str(args.stress), **stress_evidence},
        "funding": funding_status,
        "compatible_run_ids": [identity["run_id"] for identity in identities],
    }
    write_atomic_json(args.out, report)
    return report


def _exact_depth_lifecycle(
    records: Sequence[Record],
    policy_report: Mapping[str, object],
    funding: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    books = extract_observer_asset_books(records, ["SOL"])["SOL"]
    return build_eligible_exact_depth_forward_report(
        records,
        books,
        policy_report=policy_report,
        funding_evidence=funding,
        taker_fee_rate=_source_bound_taker_fee_rate(policy_report),
        maximum_entry_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
        maximum_exit_delay_ms=_MAXIMUM_BOOK_DELAY_MS,
    )


def _source_bound_taker_fee_rate(report: Mapping[str, object]) -> float:
    contract = report.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("policy report contract must be an object")
    components = contract.get("friction_components_bps")
    if not isinstance(components, Mapping):
        raise ValueError("policy report friction components must be an object")
    value = components.get("round_trip_taker_fee")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("round-trip taker fee must be numeric")
    rate = float(value) / _BPS_PER_ROUND_TRIP_RATE
    if not isfinite(rate) or rate <= 0.0 or rate >= 1.0:
        raise ValueError("derived one-way taker fee rate is invalid")
    return rate


def _profit_lock_lifecycle(
    records: Sequence[Record],
    policy_report: Mapping[str, object],
    exact_depth_report: Mapping[str, object],
) -> dict[str, object]:
    candles = build_reflection_evidence_index(records).candles.get("SOL", {})
    return build_policy_forward_profit_lock_report(
        candles,
        exact_depth_report,
        taker_fee_rate=_source_bound_taker_fee_rate(policy_report),
    )


def _funding_evidence(
    records: Sequence[Record], run_id: str
) -> tuple[EligiblePolicyFundingEvidence | None, dict[str, object]]:
    candidates, _, _ = evaluation_candidates(records)
    eligible = [
        candidate
        for candidate in candidates
        if candidate.source_run_id == run_id
        and candidate.strategy_id == _STRATEGY
        and candidate.symbol == "SOL"
        and candidate.eligible
    ]
    candles = build_candle_index(records).get("SOL", {})
    if not eligible or not candles:
        return None, {"status": "not_requested_no_eligible_path"}
    start_ms = min(candidate.available_time_ms for candidate in eligible)
    latest_observation_ms = max(
        int(timestamp(row).timestamp() * 1_000) for row in records
    )
    end_ms = max(max(candles) + MINUTE_MS, latest_observation_ms)
    try:
        evidence = _funding_reader().read("SOL", start_ms, end_ms)
    except (OSError, ValueError) as exc:
        return None, {
            "status": "unavailable",
            "technical_issue": f"{type(exc).__name__}: {exc}",
        }
    return evidence, {
        "status": "covered",
        "source": "hl_funding_history",
        "requested_start_ms": start_ms,
        "requested_end_ms": end_ms,
        "events": len(evidence.events),
    }


def _funding_reader() -> HyperliquidFundingHistoryReader:
    """Construct one unsigned public-mainnet funding reader."""
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("v49 policy monitor refuses a testnet endpoint")
    return HyperliquidFundingHistoryReader(Info(endpoint, skip_ws=True))


def _binding() -> ConfigBoundPolicyForwardBinding:
    return ConfigBoundPolicyForwardBinding(
        strategy_id=_STRATEGY,
        candidate_strategy_id=_CANDIDATE,
        symbol="SOL",
        account_value_usd=5_000.0,
    )


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def run_monitor(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn = publish_policy_checkpoint,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Publish periodically while preserving the last completed snapshot."""
    interval = float(args.interval_seconds)
    if not isfinite(interval) or interval <= 0.0:
        raise ValueError("monitor interval must be positive and finite")
    while True:
        try:
            publish_fn(args)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"v49 policy checkpoint unavailable: {exc}", file=sys.stderr)
            if args.once:
                return 2
        else:
            if args.once:
                return 0
        sleep_fn(interval)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only policy monitor with bounded error reporting."""
    try:
        return run_monitor(build_parser().parse_args(argv))
    except KeyboardInterrupt:
        return 130
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"v49 policy monitor failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
