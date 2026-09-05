#!/usr/bin/env python3
"""Continuously publish V58 HYPE alignment shadow lifecycle evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
from math import isfinite
from pathlib import Path
import time
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests.exceptions import RequestException

from hypervector.data.oxa_storage import file_evidence
from hypervector.data.jsonl_prefix import require_jsonl_prefix_unchanged
from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.live.transient_transport import transient_read_failure_reason
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    exact_depth_funding_bounds,
)
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.hype_alignment_shadow_lifecycle import (
    build_hype_alignment_shadow_resolution,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.report_only_lifecycle_watch import (
    publish_watch_status,
    report_transient_watch_failure,
    run_watch_loop,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ReportBuilder = Callable[[argparse.Namespace], dict[str, object]]
_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_LEDGER = Path("data/observe/v58_eight_asset_prospective_20260819_v1/decisions.jsonl")
_STATUS = Path("data/runtime/research/v58_hype_alignment_shadow_lifecycle_latest.json")
_SNAPSHOTS = Path(
    "data/logs/research/bidirectional_cohort/v58_hype_alignment_lifecycles"
)
_TAKER_FEE_RATE = 0.00045
_GENERATOR_PATHS = tuple(
    Path(value)
    for value in (
        __file__,
        "src/hypervector/data/jsonl_prefix.py",
        "src/hypervector/data/oxa_storage.py",
        "src/hypervector/live/hyperliquid_funding_history.py",
        "src/hypervector/research/hype_alignment_shadow_lifecycle.py",
        "src/hypervector/research/cohort_active_book_path.py",
        "src/hypervector/research/cohort_exact_depth_attempts.py",
        "src/hypervector/research/cohort_eligible_exact_depth_forward.py",
        "src/hypervector/research/cohort_eligible_exact_depth_reporting.py",
        "src/hypervector/research/cohort_eligible_opposite_exit.py",
        "src/hypervector/research/cohort_eligible_policy_funding.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_observer_exact_books.py",
        "src/hypervector/research/cohort_prospective_records.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/cohort_regime_assessment.py",
        "src/hypervector/research/v58_hype_rejected_onset_context.py",
        "src/hypervector/research/live_ledger_snapshot.py",
        "src/hypervector/research/checkpoint_storage.py",
        "src/hypervector/research/hip3_development_provenance.py",
        "src/hypervector/research/report_only_lifecycle_watch.py",
        "src/hypervector/live/cohort_maximum_hold_policy.py",
        "src/hypervector/live/hype_compression_alignment_provider.py",
        "src/hypervector/live/canonical_regime_telemetry.py",
        "src/hypervector/live/multi_asset_live_config.py",
        "src/hypervector/live/multi_asset_observer_config.py",
        "src/hypervector/live/transient_transport.py",
        "src/hypervector/runtime_lock.py",
    )
)


class FundingReaderProtocol(Protocol):
    """Unsigned official funding-history reader used by the watcher."""

    def read(
        self, symbol: str, requested_start_ms: int, requested_end_ms: int
    ) -> EligiblePolicyFundingEvidence:
        """Return complete official funding evidence for the requested path."""


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable V58 HYPE watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", type=Path, default=_STATUS)
    parser.add_argument("--snapshot-dir", type=Path, default=_SNAPSHOTS)
    parser.add_argument("--taker-fee-rate", type=float, default=_TAKER_FEE_RATE)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def watch_once(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
    funding_reader: FundingReaderProtocol | None = None,
) -> dict[str, object]:
    """Atomically refresh one exact report-only HYPE lifecycle status."""
    preregistration, prospective_start_ms = _preregistration_evidence(args)
    report = (
        report_builder(args)
        if report_builder is not None
        else _build_report(args, funding_reader, prospective_start_ms)
    )
    source = report.get("source_evidence", {})
    if not isinstance(source, Mapping):
        raise ValueError("HYPE watcher source evidence must be a mapping")
    report["source_evidence"] = {
        **source,
        "preregistration": {"path": str(args.preregistration), **preregistration},
    }
    require_unchanged_file(args.preregistration, preregistration)
    return publish_watch_status(
        report,
        status_path=args.status,
        snapshot_dir=args.snapshot_dir,
        run_id=args.run_id,
    )


def run_watcher(
    args: argparse.Namespace,
    *,
    report_builder: ReportBuilder | None = None,
    funding_reader: FundingReaderProtocol | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Refresh while enforcing one frozen loaded-generator identity."""
    frozen = _source_references(args.config)

    def refresh() -> None:
        _require_unchanged(frozen)
        watch_once(args, report_builder=report_builder, funding_reader=funding_reader)
        _require_unchanged(frozen)

    return run_watch_loop(
        refresh,
        interval_seconds=args.interval_seconds,
        max_cycles=args.max_cycles,
        sleep_fn=sleep_fn,
        transient_exceptions=(RequestException, ClientError, ServerError),
        transient_reason=transient_read_failure_reason,
        transient_reporter=report_transient_watch_failure,
    )


def _build_report(
    args: argparse.Namespace,
    funding_reader: FundingReaderProtocol | None,
    prospective_start_ms: int,
) -> dict[str, object]:
    references = _source_references(args.config)
    config = with_observer_ledger_root(
        load_multi_asset_live_config(args.config, mode="observe"),
        args.ledger.parent,
    )
    if config.cohort_ledger.resolve() != args.ledger.resolve():
        raise ValueError("HYPE watcher ledger differs from observer config binding")
    with snapshot_decision_ledger(args.ledger, allow_incomplete_tail=True) as source:
        initial = _resolution(source[0], config, args, prospective_start_ms, None)
        funding = _funding(funding_reader, exact_depth_funding_bounds(initial))
        report = _resolution(source[0], config, args, prospective_start_ms, funding)
    _require_unchanged(references)
    report["source_evidence"] = {
        "ledger": {"path": str(args.ledger), **source[1]},
        "config": {"path": str(args.config), **references[args.config]},
        "generators": _generator_evidence(references, args.config),
        "funding": _funding_payload(funding),
    }
    return report


def _resolution(
    records: Sequence[Mapping[str, object]],
    config: MultiAssetLiveConfig,
    args: argparse.Namespace,
    prospective_start_ms: int,
    funding: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    return build_hype_alignment_shadow_resolution(
        records,
        config=config,
        run_id=args.run_id,
        prospective_start_ms=prospective_start_ms,
        funding_evidence=funding,
        taker_fee_rate=_fee_rate(args.taker_fee_rate),
    )


def _funding(
    reader: FundingReaderProtocol | None,
    bounds: tuple[int, int] | None,
) -> EligiblePolicyFundingEvidence | None:
    if bounds is None:
        return None
    source = reader or _funding_reader()
    return source.read("HYPE", bounds[0], bounds[1])


def _funding_reader() -> HyperliquidFundingHistoryReader:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("HYPE watcher refuses a testnet endpoint")
    return HyperliquidFundingHistoryReader(Info(endpoint, skip_ws=True))


def _source_references(config: Path) -> dict[Path, dict[str, object]]:
    paths = (config, *_GENERATOR_PATHS)
    return {path: file_evidence(path) for path in paths}


def _require_unchanged(references: dict[Path, dict[str, object]]) -> None:
    for path, evidence in references.items():
        require_unchanged_file(path, evidence)


def _generator_evidence(
    references: dict[Path, dict[str, object]], config: Path
) -> list[dict[str, object]]:
    return [
        {"path": str(path), **evidence}
        for path, evidence in references.items()
        if path != config and path.suffix == ".py"
    ]


def _preregistration_evidence(
    args: argparse.Namespace,
) -> tuple[dict[str, object], int]:
    evidence = file_evidence(args.preregistration)
    expected = args.preregistration_sha256
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("HYPE watcher preregistration hash must be exact SHA-256")
    if evidence.get("sha256") != expected:
        raise ValueError("HYPE watcher preregistration hash does not match")
    value = json.loads(args.preregistration.read_text(encoding="utf-8"))
    safe = (
        isinstance(value, dict)
        and value.get("report_only") is True
        and value.get("execution_authority") == "none"
        and value.get("automatic_live_change") is False
        and value.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("HYPE watcher preregistration authority is invalid")
    prefix = value.get("ledger_prefix")
    if not isinstance(prefix, Mapping):
        raise ValueError("HYPE watcher preregistration ledger prefix is missing")
    require_jsonl_prefix_unchanged(args.ledger, prefix, "HYPE preregistered ledger")
    start = value.get("prospective_start_ms")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError("HYPE watcher prospective start must be nonnegative")
    return evidence, start


def _funding_payload(
    funding: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    if funding is None:
        return {"status": "not_requested_no_entered_lifecycle"}
    return {
        "status": "covered",
        "source": "hl_funding_history",
        "symbol": funding.symbol,
        "requested_start_ms": funding.requested_start_ms,
        "requested_end_ms": funding.requested_end_ms,
        "events": [
            {"timestamp_ms": row.timestamp_ms, "funding_rate": row.funding_rate}
            for row in funding.events
        ],
    }


def _fee_rate(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("HYPE watcher taker fee rate must be numeric")
    output = float(value)
    if not isfinite(output) or not 0.0 < output < 1.0:
        raise ValueError("HYPE watcher taker fee rate must be finite and positive")
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton report-only HYPE lifecycle watcher."""
    args = build_parser().parse_args(argv)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
