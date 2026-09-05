#!/usr/bin/env python3
"""Capture immutable report-only evidence after a cohort's first live event."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_first_event_capture import (
    CaptureStage,
    CapturePaths,
    FirstEventTrigger,
    build_capture_trigger,
    build_manifest,
    capture_required,
    capture_paths,
    capture_waiting_state,
    status_payload,
    validate_audit,
    validate_baseline,
    validate_delta,
    validate_manifest,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

Record = Mapping[str, object]
CommandRunner = Callable[[tuple[str, ...]], None]

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable first-event watcher parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/runtime/bidirectional_cohort/latest_checkpoint.json"),
    )
    parser.add_argument("--decision-overrides", type=Path, required=True)
    parser.add_argument(
        "--ledger-root",
        type=Path,
        default=Path("data/live/bidirectional_cohort"),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument(
        "--terminal-state",
        choices=("first_event", "resolved_lifecycle"),
        default="first_event",
    )
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def capture_once(
    args: argparse.Namespace,
    *,
    command_runner: CommandRunner,
) -> dict[str, object]:
    """Evaluate one source snapshot and capture the first event exactly once."""
    checkpoint = _load(args.checkpoint, "checkpoint")
    overrides_evidence = file_evidence(args.decision_overrides)
    overrides = _load(args.decision_overrides, "decision overrides")
    trigger = build_capture_trigger(checkpoint, overrides, args.hypothesis_id)
    validate_baseline(trigger.baseline_path, trigger.identity)
    baseline_evidence = file_evidence(trigger.baseline_path)
    validate_baseline(trigger.baseline_path, trigger.identity)
    capture_stage = _capture_stage(args)
    paths = capture_paths(args.out_dir, trigger, capture_stage)
    if paths.manifest.is_file():
        validate_manifest(paths.manifest, trigger, capture_stage)
        return _publish_status(
            args.status, trigger, "already_captured", capture_stage, paths.manifest
        )
    if not capture_required(trigger, capture_stage):
        return _publish_status(
            args.status,
            trigger,
            capture_waiting_state(capture_stage),
            capture_stage,
        )
    _capture_bundle(
        args,
        trigger,
        paths,
        capture_stage,
        command_runner,
        overrides_evidence,
        baseline_evidence,
    )
    return _publish_status(
        args.status, trigger, "captured", capture_stage, paths.manifest
    )


def run_watcher(
    args: argparse.Namespace,
    *,
    command_runner: CommandRunner | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Poll until captured, once requested, or a bounded cycle limit is reached."""
    _validate_loop_args(args)
    runner = _run_command if command_runner is None else command_runner
    cycles = 0
    while True:
        status = capture_once(args, command_runner=runner)
        cycles += 1
        if status["state"] in {"captured", "already_captured"}:
            return 0
        if args.once or (args.max_cycles and cycles >= args.max_cycles):
            return 0
        sleep_fn(args.interval_seconds)


def _capture_bundle(
    args: argparse.Namespace,
    trigger: FirstEventTrigger,
    paths: CapturePaths,
    capture_stage: CaptureStage,
    command_runner: CommandRunner,
    overrides_evidence: Mapping[str, object],
    baseline_evidence: Mapping[str, object],
) -> None:
    paths.directory.mkdir(parents=True, exist_ok=True)
    _require_source_snapshot(
        paths.directory / "source_snapshot.json",
        _source_snapshot(
            args,
            trigger,
            capture_stage,
            overrides_evidence,
            baseline_evidence,
        ),
    )
    if not paths.after_audit.exists():
        command_runner(_audit_command(args, trigger, paths))
    validate_audit(paths.after_audit, trigger.identity)
    if not paths.delta.exists():
        command_runner(_delta_command(trigger, paths))
    validate_delta(paths.delta, trigger.identity)
    _require_unchanged(
        args.decision_overrides,
        overrides_evidence,
        "decision overrides",
    )
    _require_unchanged(
        trigger.baseline_path,
        baseline_evidence,
        "baseline audit",
    )
    manifest = build_manifest(
        trigger,
        checkpoint_path=args.checkpoint,
        overrides_path=args.decision_overrides,
        paths=paths,
        capture_stage=capture_stage,
    )
    write_immutable_json(paths.manifest, manifest)


def _source_snapshot(
    args: argparse.Namespace,
    trigger: FirstEventTrigger,
    capture_stage: CaptureStage,
    overrides_evidence: Mapping[str, object],
    baseline_evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_first_event_source_snapshot",
        "hypothesis_id": trigger.hypothesis_id,
        "capture_stage": capture_stage,
        "identity": dict(trigger.identity),
        "decision_overrides": {
            "path": str(args.decision_overrides),
            **dict(overrides_evidence),
        },
        "baseline_audit": {
            "path": str(trigger.baseline_path),
            **dict(baseline_evidence),
        },
    }


def _require_source_snapshot(path: Path, expected: Mapping[str, object]) -> None:
    if not path.exists():
        write_immutable_json(path, dict(expected))
        return
    if _load(path, "capture source snapshot") != expected:
        raise ValueError("capture source snapshot mismatch")


def _require_unchanged(
    path: Path,
    expected: Mapping[str, object],
    label: str,
) -> None:
    if file_evidence(path) != expected:
        raise ValueError(f"{label} changed during first-event capture")


def _audit_command(
    args: argparse.Namespace,
    trigger: FirstEventTrigger,
    paths: CapturePaths,
) -> tuple[str, ...]:
    return (
        sys.executable,
        str(_SCRIPTS / "multi_asset_bidirectional_live_audit.py"),
        "--ledger-root",
        str(args.ledger_root),
        "--run-id",
        trigger.identity["run_id"],
        "--out",
        str(paths.after_audit),
        "--history-scope",
        "current-run",
    )


def _delta_command(
    trigger: FirstEventTrigger,
    paths: CapturePaths,
) -> tuple[str, ...]:
    return (
        sys.executable,
        str(_SCRIPTS / "cohort_live_audit_delta.py"),
        "--before",
        str(trigger.baseline_path),
        "--after",
        str(paths.after_audit),
        "--out",
        str(paths.delta),
    )


def _publish_status(
    path: Path,
    trigger: FirstEventTrigger,
    state: str,
    capture_stage: CaptureStage,
    manifest: Path | None = None,
) -> dict[str, object]:
    payload = status_payload(
        trigger,
        state=state,
        manifest_path=manifest,
        capture_stage=capture_stage,
    )
    write_atomic_json(path, payload)
    return payload


def _run_command(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True, text=True, capture_output=True)


def _load(path: Path, label: str) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _validate_loop_args(args: argparse.Namespace) -> None:
    interval = args.interval_seconds
    if not isinstance(interval, (int, float)) or not math.isfinite(interval):
        raise ValueError("interval seconds must be finite")
    if interval <= 0:
        raise ValueError("interval seconds must be positive")
    if (
        isinstance(args.max_cycles, bool)
        or not isinstance(args.max_cycles, int)
        or args.max_cycles < 0
    ):
        raise ValueError("max cycles must be a nonnegative integer")
    _capture_stage(args)


def _capture_stage(args: argparse.Namespace) -> CaptureStage:
    value = getattr(args, "terminal_state", "first_event")
    if value not in {"first_event", "resolved_lifecycle"}:
        raise ValueError("terminal state must be first_event or resolved_lifecycle")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run the watcher without constructing execution or signing clients."""
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
        print(f"first-event capture refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
