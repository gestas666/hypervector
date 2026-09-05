#!/usr/bin/env python3
"""Continuously publish the exact authority-none V58 ETH lifecycle."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
import time

from eth_pullback_forward_resolution import build_report
from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests.exceptions import RequestException

from hypervector.data.jsonl_prefix import require_jsonl_prefix_unchanged
from hypervector.data.oxa_storage import file_evidence
from hypervector.live.transient_transport import transient_read_failure_reason
from hypervector.research.hip3_development_provenance import require_unchanged_file
from hypervector.research.report_only_lifecycle_watch import (
    publish_watch_status,
    report_transient_watch_failure,
    run_watch_loop,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ReportBuilder = Callable[[argparse.Namespace], dict[str, object]]
_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_ROOT = Path("data/observe/v58_eight_asset_prospective_20260819_v1")
_LEDGER = _ROOT / "decisions.jsonl"
_STATUS = Path("data/runtime/research/v58_eth_pullback_first_lifecycle_latest.json")
_SNAPSHOTS = Path("data/logs/research/bidirectional_cohort/v58_eth_pullback_lifecycles")
_TAKER_FEE_RATE = 0.00045
_GENERATOR_PATHS = tuple(
    Path(value)
    for value in (
        __file__,
        "scripts/eth_pullback_forward_resolution.py",
        "src/hypervector/research/eth_pullback_forward_resolution.py",
        "src/hypervector/research/cohort_active_book_path.py",
        "src/hypervector/research/cohort_exact_depth_attempts.py",
        "src/hypervector/research/cohort_eligible_exact_depth_forward.py",
        "src/hypervector/research/cohort_eligible_exact_depth_reporting.py",
        "src/hypervector/research/cohort_eligible_opposite_exit.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/cohort_eligible_policy_funding.py",
        "src/hypervector/research/cohort_observer_exact_books.py",
        "src/hypervector/research/cohort_prospective_records.py",
        "src/hypervector/research/cohort_live_audit_values.py",
        "src/hypervector/research/market_depth_fill.py",
        "src/hypervector/research/report_only_lifecycle_watch.py",
        "src/hypervector/live/transient_transport.py",
    )
)


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable ETH lifecycle watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--ledger", type=Path, default=_LEDGER)
    parser.add_argument("--observer-ledger-root", type=Path, default=_ROOT)
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
) -> dict[str, object]:
    """Atomically refresh one exact report-only ETH lifecycle status."""
    preregistration, prospective_start_ms = _preregistration_evidence(args)
    references = _generator_references()
    report = (
        report_builder(args)
        if report_builder
        else build_report(args, prospective_start_ms=prospective_start_ms)
    )
    source = report.get("source_evidence", {})
    if not isinstance(source, Mapping):
        raise ValueError("ETH watcher source evidence must be a mapping")
    report["source_evidence"] = {
        **source,
        "preregistration": {"path": str(args.preregistration), **preregistration},
        "watcher_generators": _generator_payload(references),
    }
    _require_unchanged({args.preregistration: preregistration, **references})
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
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Run against one frozen generator identity until bounded completion."""
    frozen = _generator_references()

    def refresh() -> None:
        _require_unchanged(frozen)
        watch_once(args, report_builder=report_builder)
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


def _preregistration_evidence(
    args: argparse.Namespace,
) -> tuple[dict[str, object], int]:
    evidence = file_evidence(args.preregistration)
    expected = args.preregistration_sha256
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("ETH watcher preregistration hash must be exact SHA-256")
    if evidence.get("sha256") != expected:
        raise ValueError("ETH watcher preregistration hash does not match")
    value = json.loads(args.preregistration.read_text(encoding="utf-8"))
    _require_preregistration_contract(value, args)
    frozen = value.get("frozen_identity")
    if not isinstance(frozen, Mapping):
        raise ValueError("ETH watcher preregistration identity is missing")
    prospective_start_ms = frozen.get("prospective_start_ms")
    if (
        isinstance(prospective_start_ms, bool)
        or not isinstance(prospective_start_ms, int)
        or prospective_start_ms < 0
    ):
        raise ValueError("ETH watcher prospective start must be nonnegative")
    prefix = value.get("ledger_prefix")
    if not isinstance(prefix, Mapping):
        raise ValueError("ETH watcher preregistration ledger prefix is missing")
    require_jsonl_prefix_unchanged(args.ledger, prefix, "ETH preregistered ledger")
    return evidence, prospective_start_ms


def _require_preregistration_contract(value: object, args: argparse.Namespace) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("ETH watcher preregistration must be a mapping")
    authority = value.get("authority")
    frozen = value.get("frozen_identity")
    safe = (
        value.get("strategy_id")
        == "eth_breakout_precompression_pullback_bidirectional_v1"
        and value.get("symbol") == "ETH"
        and isinstance(authority, Mapping)
        and authority.get("report_only") is True
        and authority.get("execution_authority") == "none"
        and authority.get("runtime_strategy_changed") is False
        and isinstance(frozen, Mapping)
        and frozen.get("observer_run_id") == args.run_id
    )
    if not safe:
        raise ValueError("ETH watcher preregistration authority or identity is invalid")
    _require_config_evidence(value, args.config)


def _require_config_evidence(value: Mapping[str, object], config: Path) -> None:
    rows = value.get("source_evidence")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("ETH watcher preregistration source evidence is missing")
    current = file_evidence(config)
    matched = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and isinstance(row.get("path"), str)
        and Path(str(row["path"])).resolve() == config.resolve()
    ]
    if len(matched) != 1 or matched[0].get("sha256") != current.get("sha256"):
        raise ValueError("ETH watcher preregistration config evidence differs")


def _generator_references() -> dict[Path, dict[str, object]]:
    return {path: file_evidence(path) for path in _GENERATOR_PATHS}


def _generator_payload(
    references: Mapping[Path, Mapping[str, object]],
) -> list[dict[str, object]]:
    return [{"path": str(path), **evidence} for path, evidence in references.items()]


def _require_unchanged(
    references: Mapping[Path, Mapping[str, object]],
) -> None:
    for path, evidence in references.items():
        require_unchanged_file(path, evidence)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton ETH watcher without execution authority."""
    args = build_parser().parse_args(argv)
    try:
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
