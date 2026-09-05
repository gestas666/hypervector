#!/usr/bin/env python3
"""Finalize one predeclared MU transport-parity window without authority."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.mu_transport_parity_finalizer import (
    MuTransportWindowSpec,
    ObserverWindowProgress,
    load_window_spec,
    read_observer_progress,
    validate_frozen_generators,
)
from hypervector.research.mu_transport_parity_publication import (
    CommandRunner,
    MuFinalizationInputs,
    load_existing_manifest,
    manifest_path,
    publish_chain_failure,
    publish_complete,
    publish_missing_failure,
    publish_source_failure,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

Record = Mapping[str, object]
_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable fixed-window finalizer parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prereg",
        type=Path,
        default=Path(
            "docs/research-journal/v52-mu-transport-parity-forward-window-v1.json"
        ),
    )
    parser.add_argument(
        "--observer-journal",
        type=Path,
        default=Path("data/live/research/mu_hip3_breakout_shadow.jsonl"),
    )
    parser.add_argument("--source-hash-correction", type=Path)
    parser.add_argument("--development-diagnostic", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def finalize_once(
    args: argparse.Namespace,
    *,
    now_ms: int,
    command_runner: CommandRunner,
) -> dict[str, object]:
    """Inspect one source prefix and finalize only after the frozen boundary."""
    spec = load_window_spec(Path(args.prereg))
    inputs = _inputs(args)
    existing = load_existing_manifest(inputs, spec)
    if existing is not None:
        return _existing_status(args, spec, existing, manifest_path(inputs, spec))
    progress = read_observer_progress(inputs.observer_journal, spec)
    try:
        validate_frozen_generators(
            spec, inputs.root, correction_path=inputs.source_hash_correction
        )
    except (FileNotFoundError, ValueError) as exc:
        return _handle_source_failure(args, inputs, spec, progress, now_ms, exc)
    if now_ms < spec.end_exclusive_ms:
        status = _status(spec, progress, "collecting", now_ms=now_ms)
        return _publish_status(args.status, status)
    if not progress.complete:
        manifest = publish_missing_failure(inputs, spec, progress)
        return _final_status(args, spec, progress, manifest, "FAIL")
    try:
        manifest, verdict = publish_complete(inputs, spec, progress, command_runner)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        manifest = publish_chain_failure(inputs, spec, progress, exc)
        verdict = "FAIL"
    return _final_status(args, spec, progress, manifest, verdict)


def _inputs(args: argparse.Namespace) -> MuFinalizationInputs:
    return MuFinalizationInputs(
        prereg=Path(args.prereg),
        observer_journal=Path(args.observer_journal),
        development_diagnostic=Path(args.development_diagnostic),
        data_root=Path(args.data_root),
        out_dir=Path(args.out_dir),
        root=Path(args.root),
        source_hash_correction=(
            None
            if getattr(args, "source_hash_correction", None) is None
            else Path(args.source_hash_correction)
        ),
    )


def _handle_source_failure(
    args: argparse.Namespace,
    inputs: MuFinalizationInputs,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    now_ms: int,
    error: Exception,
) -> dict[str, object]:
    if now_ms < spec.end_exclusive_ms:
        status = _status(spec, progress, "collecting_source_failure", now_ms=now_ms)
        status["pending_failure_reason"] = "frozen_generator_changed"
        status["failure_detail"] = str(error)
        return _publish_status(args.status, status)
    manifest = publish_source_failure(inputs, spec, progress, error)
    return _final_status(args, spec, progress, manifest, "FAIL")


def _final_status(
    args: argparse.Namespace,
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    manifest: Path,
    verdict: str,
) -> dict[str, object]:
    state = "finalized_pass" if verdict == "PASS" else "finalized_fail"
    status = _status(spec, progress, state)
    status["manifest_path"] = str(manifest)
    return _publish_status(args.status, status)


def _existing_status(
    args: argparse.Namespace,
    spec: MuTransportWindowSpec,
    report: Record,
    path: Path,
) -> dict[str, object]:
    verdict = report.get("verdict")
    progress = _mapping(report, "observer_progress")
    payload = _status_from_record(
        spec, progress, f"already_finalized_{str(verdict).lower()}"
    )
    payload["manifest_path"] = str(path)
    return _publish_status(args.status, payload)


def _status(
    spec: MuTransportWindowSpec,
    progress: ObserverWindowProgress,
    state: str,
    *,
    now_ms: int | None = None,
) -> dict[str, object]:
    status = _status_from_record(
        spec,
        {
            "observed_decisions": progress.observed_decisions,
            "resolved_decisions": progress.resolved_decisions,
            "eligible_decisions": progress.eligible_decisions,
        },
        state,
    )
    status.update(_past_due_status(progress, now_ms))
    return status


def _past_due_status(
    progress: ObserverWindowProgress,
    now_ms: int | None,
) -> dict[str, object]:
    missing = [] if now_ms is None else _past_due(progress.missing_decisions, now_ms)
    unresolved = (
        [] if now_ms is None else _past_due(progress.unresolved_decisions, now_ms)
    )
    alert = None
    if missing:
        alert = "missing_past_decision"
    elif unresolved:
        alert = "unresolved_past_decision"
    return {
        "past_due_missing_decisions": missing,
        "past_due_unresolved_decisions": unresolved,
        "technical_alert": alert,
    }


def _past_due(decisions: tuple[int, ...], now_ms: int) -> list[int]:
    return [decision for decision in decisions if decision < now_ms]


def _status_from_record(
    spec: MuTransportWindowSpec,
    progress: Record,
    state: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "mu_transport_parity_fixed_window_finalizer",
        "state": state,
        "hypothesis_id": spec.hypothesis_id,
        "symbol": spec.symbol,
        "window_start_ms": spec.start_ms,
        "window_end_exclusive_ms": spec.end_exclusive_ms,
        "expected_decisions": spec.expected_decisions,
        "observed_decisions": progress.get("observed_decisions"),
        "resolved_decisions": progress.get("resolved_decisions"),
        "eligible_decisions": progress.get("eligible_decisions"),
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }


def run_watcher(
    args: argparse.Namespace,
    *,
    command_runner: CommandRunner | None = None,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Poll the immutable window until publication or a bounded stop."""
    _validate_loop_args(args)
    runner = _run_command if command_runner is None else command_runner
    prereg = Path(args.prereg)
    prereg_evidence = file_evidence(prereg)
    cycles = 0
    while True:
        _require_preregistration_unchanged(prereg, prereg_evidence)
        status = finalize_once(
            args,
            now_ms=clock_ms(),
            command_runner=lambda command: _run_frozen(
                command, runner, prereg, prereg_evidence
            ),
        )
        _require_preregistration_unchanged(prereg, prereg_evidence)
        cycles += 1
        state = str(status.get("state", ""))
        if state in {"finalized_pass", "already_finalized_pass"}:
            return 0
        if state in {"finalized_fail", "already_finalized_fail"}:
            return 2
        if args.once or (args.max_cycles and cycles >= args.max_cycles):
            return 0
        sleep_fn(args.interval_seconds)


def _run_frozen(
    command: tuple[str, ...],
    runner: CommandRunner,
    prereg: Path,
    expected: Record,
) -> None:
    _require_preregistration_unchanged(prereg, expected)
    runner(command)
    _require_preregistration_unchanged(prereg, expected)


def _require_preregistration_unchanged(path: Path, expected: Record) -> None:
    if file_evidence(path) != expected:
        raise RuntimeError("MU transport preregistration changed after watcher start")


def _publish_status(path: Path, payload: dict[str, object]) -> dict[str, object]:
    write_atomic_json(path, payload)
    return payload


def _run_command(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True, text=True, capture_output=True)


def _validate_loop_args(args: argparse.Namespace) -> None:
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("interval seconds must be finite")
    if interval <= 0:
        raise ValueError("interval seconds must be positive")
    if isinstance(args.max_cycles, bool) or not isinstance(args.max_cycles, int):
        raise ValueError("max cycles must be a nonnegative integer")
    if args.max_cycles < 0:
        raise ValueError("max cycles must be a nonnegative integer")


def _mapping(parent: Record, key: str) -> Record:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"MU finalization {key} must be an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only finalizer."""
    try:
        args = build_parser().parse_args(argv)
        with cohort_checkpoint_runtime_lock(args.status):
            return run_watcher(args)
    except KeyboardInterrupt:
        return 130
    except (
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"MU transport finalizer refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
