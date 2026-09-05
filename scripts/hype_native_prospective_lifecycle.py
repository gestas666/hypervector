#!/usr/bin/env python3
"""Publish immutable report-only HYPE-native prospective lifecycle evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from hashlib import sha256
import json
import math
from pathlib import Path
import time

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hype_native_prospective_lifecycle import (
    HypeNativeProspectiveSpec,
    build_hype_native_prospective_report,
)
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

_GENERATOR_FILES = tuple(
    Path(value).resolve()
    for value in (
        __file__,
        "src/hypervector/research/hype_native_baseline_comparison.py",
        "src/hypervector/research/hype_native_prospective_lifecycle.py",
        "src/hypervector/research/hype_native_prospective_metrics.py",
        "src/hypervector/research/cohort_exact_depth_books.py",
        "src/hypervector/research/cohort_observer_exact_books.py",
        "src/hypervector/research/cohort_signal_candidates.py",
        "src/hypervector/research/live_ledger_snapshot.py",
        "src/hypervector/research/market_depth_fill.py",
        "src/hypervector/data/oxa_storage.py",
    )
)


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable prospective lifecycle parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-fingerprint", required=True)
    parser.add_argument("--run-fingerprint", required=True)
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--notional-usd", type=float, required=True)
    parser.add_argument("--stop-bps", type=float, required=True)
    parser.add_argument("--maximum-hold-seconds", type=int, required=True)
    parser.add_argument("--maximum-entry-delay-ms", type=int, required=True)
    parser.add_argument("--maximum-exit-delay-ms", type=int, required=True)
    parser.add_argument("--fee-bps-per-side", type=float, required=True)
    parser.add_argument("--residual-slippage-bps-per-side", type=float, required=True)
    parser.add_argument("--maximum-book-gap-ms", type=int, required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path)
    destination.add_argument("--status", type=Path)
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser


def publish_report(args: argparse.Namespace) -> dict[str, object]:
    """Freeze the observer prefix and publish one immutable proxy report."""
    if args.out.exists():
        raise FileExistsError(f"prospective HYPE output exists: {args.out}")
    report = _build_report(args)
    write_immutable_json(args.out, report)
    return report


def watch_once(args: argparse.Namespace) -> dict[str, object]:
    """Refresh one atomic status without creating execution authority."""
    report = _build_report(args)
    state_id = _state_id(report)
    snapshot = _snapshot_state(args, report, state_id)
    status = {
        **report,
        "observed_at_ms": int(time.time() * 1_000),
        "watch_state": report["status"],
        "watch_state_id": state_id,
        "snapshot": snapshot,
    }
    write_atomic_json(args.status, status)
    return status


def run_watcher(
    args: argparse.Namespace,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Continuously refresh report-only status or stop at a bounded cycle count."""
    _validate_watch_args(args)
    cycles = 0
    while True:
        watch_once(args)
        cycles += 1
        if args.max_cycles and cycles >= args.max_cycles:
            return 0
        sleep_fn(args.interval_seconds)


def _build_report(args: argparse.Namespace) -> dict[str, object]:
    config = _config_evidence(args.config, args.config_sha256)
    generator = _generator_identity()
    with snapshot_decision_ledger(args.decisions, run_id=args.run_id) as source:
        report = build_hype_native_prospective_report(source[0], _spec(args))
    report["evidence"] = {
        "decision_ledger": {"path": str(args.decisions), **source[1]},
        "config": {"path": str(args.config), **config},
    }
    report["generator_identity"] = {"files": generator}
    if config != _config_evidence(args.config, args.config_sha256):
        raise RuntimeError("prospective HYPE config changed during evaluation")
    if generator != _generator_identity():
        raise RuntimeError("prospective HYPE generator changed during evaluation")
    return report


def _state_id(report: dict[str, object]) -> str:
    selected = {
        field: report.get(field)
        for field in (
            "status",
            "signal_counts",
            "attempts",
            "lifecycles",
            "baseline_comparisons",
            "resolved_proxy_summary",
        )
    }
    raw = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return sha256(raw).hexdigest()


def _snapshot_state(
    args: argparse.Namespace,
    report: dict[str, object],
    state_id: str,
) -> str | None:
    trades = _closed_trades(report)
    if trades == 0:
        return None
    path = args.snapshot_dir / f"{args.run_id}_{trades:04d}_{state_id[:12]}.json"
    payload = {**report, "watch_state_id": state_id}
    if path.exists():
        observed = json.loads(path.read_text(encoding="utf-8"))
        _require_matching_snapshot(observed, report, state_id)
    else:
        write_immutable_json(path, payload)
    return str(path)


def _require_matching_snapshot(
    observed: object,
    report: dict[str, object],
    state_id: str,
) -> None:
    if not isinstance(observed, dict):
        raise ValueError("prospective HYPE snapshot must be an object")
    if observed.get("watch_state_id") != state_id or _state_id(observed) != state_id:
        raise ValueError("prospective HYPE snapshot material state differs")
    for field in ("identity", "contract"):
        if observed.get(field) != report.get(field):
            raise ValueError(f"prospective HYPE snapshot {field} differs")


def _closed_trades(report: dict[str, object]) -> int:
    summary = report.get("resolved_proxy_summary")
    if not isinstance(summary, dict):
        raise ValueError("prospective HYPE summary must be an object")
    trades = summary.get("trades")
    if isinstance(trades, bool) or not isinstance(trades, int) or trades < 0:
        raise ValueError("prospective HYPE closed trades must be nonnegative")
    return trades


def _validate_watch_args(args: argparse.Namespace) -> None:
    if args.status is None or args.snapshot_dir is None:
        raise ValueError("prospective HYPE watch requires status and snapshot dir")
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("prospective HYPE watch interval must be finite")
    if interval <= 0.0:
        raise ValueError("prospective HYPE watch interval must be positive")
    if (
        isinstance(args.max_cycles, bool)
        or not isinstance(args.max_cycles, int)
        or args.max_cycles < 0
    ):
        raise ValueError("prospective HYPE max cycles must be nonnegative")


def _spec(args: argparse.Namespace) -> HypeNativeProspectiveSpec:
    return HypeNativeProspectiveSpec(
        run_id=args.run_id,
        profile_id=args.profile_id,
        profile_fingerprint=args.profile_fingerprint,
        run_fingerprint=args.run_fingerprint,
        strategy_id=args.strategy_id,
        symbol="HYPE",
        notional_usd=args.notional_usd,
        stop_bps=args.stop_bps,
        maximum_hold_seconds=args.maximum_hold_seconds,
        maximum_entry_delay_ms=args.maximum_entry_delay_ms,
        maximum_exit_delay_ms=args.maximum_exit_delay_ms,
        fee_bps_per_side=args.fee_bps_per_side,
        residual_slippage_bps_per_side=args.residual_slippage_bps_per_side,
        maximum_book_gap_ms=args.maximum_book_gap_ms,
    )


def _config_evidence(path: Path, expected_sha256: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"prospective HYPE config does not exist: {path}")
    evidence = file_evidence(path)
    if evidence["sha256"] != expected_sha256:
        raise ValueError("prospective HYPE config SHA-256 differs")
    return evidence


def _generator_identity() -> list[dict[str, object]]:
    return [_file_record(path) for path in _GENERATOR_FILES]


def _file_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv: Sequence[str] | None = None) -> int:
    """Publish evidence without constructing a signer or exchange client."""
    args = build_parser().parse_args(argv)
    if args.status is not None:
        try:
            with cohort_checkpoint_runtime_lock(args.status):
                return run_watcher(args)
        except KeyboardInterrupt:
            return 130
    report = publish_report(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_only": True,
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
