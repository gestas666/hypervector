#!/usr/bin/env python3
"""Publish dual-MTF exit evidence only when an exact v39 close appears."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from hypervector.research.checkpoint_storage import write_atomic_json

Record = Mapping[str, object]
PublishFn = Callable[[argparse.Namespace, Path], None]
SleepFn = Callable[[float], None]

_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_LEDGER_ROOT = Path("data/live/bidirectional_cohort")
_BOOTSTRAP = Path(
    "data/logs/research/bidirectional_cohort/"
    "v39_dual_mtf_profit_reversal_exit_20260811T204800Z_v3.json"
)
_CURSOR = Path(
    "data/runtime/bidirectional_cohort/v39_dual_mtf_reversal_monitor_cursor.json"
)
_ARTIFACT_DIR = Path("data/logs/research/bidirectional_cohort")
_CHALLENGER = Path("scripts/cohort_dual_mtf_reversal_exit.py")


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable close-triggered monitor contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--ledger-root", type=Path, default=_LEDGER_ROOT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile-fingerprint", required=True)
    parser.add_argument("--bootstrap-artifact", type=Path, default=_BOOTSTRAP)
    parser.add_argument("--cursor", type=Path, default=_CURSOR)
    parser.add_argument("--artifact-dir", type=Path, default=_ARTIFACT_DIR)
    parser.add_argument("--challenger-script", type=Path, default=_CHALLENGER)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    return parser


def refresh(
    args: argparse.Namespace,
    *,
    publish_fn: PublishFn | None = None,
) -> dict[str, object]:
    """Initialize or publish after an increase in exact-run closed trades."""
    _validate_args(args)
    checkpoint = _read_mapping(args.checkpoint, "v39 checkpoint")
    closed = _checkpoint_closed_trades(checkpoint, args)
    cursor, initialized = _load_or_initialize_cursor(args)
    prior = _cursor_closed_trades(cursor, args)
    if closed < prior:
        raise ValueError("v39 closed-trade count regressed below monitor cursor")
    if closed == prior:
        state = "initialized" if initialized else "unchanged"
        return _result(state, closed, cursor)
    output = _artifact_path(args.artifact_dir)
    (publish_fn or _publish_subprocess)(args, output)
    artifact = _artifact_contract(output, args)
    if artifact["closed_trades"] != closed:
        raise ValueError("challenger artifact closed count differs from checkpoint")
    updated = _cursor_payload(args, closed, output)
    write_atomic_json(args.cursor, updated)
    return _result("published", closed, updated)


def run_monitor(
    args: argparse.Namespace,
    *,
    sleep_fn: SleepFn = time.sleep,
    publish_fn: PublishFn | None = None,
) -> int:
    """Poll without advancing durable state after a technical failure."""
    _validate_args(args)
    completed = 0
    while True:
        try:
            result = refresh(args, publish_fn=publish_fn)
        except _EXPECTED_FAILURES as exc:
            _emit("unavailable", error=f"{type(exc).__name__}: {exc}")
            if args.once:
                return 2
        else:
            completed += 1
            _emit(str(result["state"]), closed_trades=result["closed_trades"])
            if args.once or (args.max_cycles and completed >= args.max_cycles):
                return 0
        sleep_fn(args.interval_seconds)


def _load_or_initialize_cursor(
    args: argparse.Namespace,
) -> tuple[dict[str, object], bool]:
    if args.cursor.is_file():
        return dict(_read_mapping(args.cursor, "dual-MTF cursor")), False
    artifact = _artifact_contract(args.bootstrap_artifact, args)
    payload = _cursor_payload(
        args,
        int(artifact["closed_trades"]),
        args.bootstrap_artifact,
    )
    write_atomic_json(args.cursor, payload)
    return payload, True


def _checkpoint_closed_trades(
    checkpoint: Record,
    args: argparse.Namespace,
) -> int:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    if lifecycle.get("state") != "running_consistent":
        raise ValueError("v39 checkpoint is not running_consistent")
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError("v39 checkpoint configuration does not match runtime")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    run = _mapping(audit.get("run"), "checkpoint run")
    _require_identity(run, args, "checkpoint")
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    trades = _records(reflections.get("trades"), "closed trade reflections")
    return sum(row.get("source_run_id") == args.run_id for row in trades)


def _artifact_contract(path: Path, args: argparse.Namespace) -> dict[str, object]:
    artifact = _read_mapping(path, "dual-MTF artifact")
    contract = _mapping(artifact.get("contract"), "challenger contract")
    required = {
        "automatic_promotion": False,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "selected_policy": None,
    }
    for field, expected in required.items():
        if contract.get(field) != expected:
            raise ValueError(f"challenger contract {field} is invalid")
    profile = _mapping(artifact.get("current_profile"), "current profile")
    if profile.get("source_profile_fingerprint") != args.profile_fingerprint:
        raise ValueError("challenger artifact profile identity does not match")
    current = _mapping(artifact.get("current_run"), "current run")
    if current.get("source_run_id") != args.run_id:
        raise ValueError("challenger artifact run identity does not match")
    return {"closed_trades": _policy_closed_count(current)}


def _policy_closed_count(current: Record) -> int:
    policies = _mapping(current.get("policies"), "current-run policies")
    counts: set[int] = set()
    for policy in policies.values():
        row = _mapping(policy, "current-run policy")
        eligible = _nonnegative_int(row.get("eligible_lifecycles"), "eligible")
        withheld = _nonnegative_int(row.get("withheld_lifecycles"), "withheld")
        counts.add(eligible + withheld)
    if len(counts) != 1:
        raise ValueError("challenger policies disagree on closed lifecycle count")
    return counts.pop()


def _cursor_closed_trades(cursor: Record, args: argparse.Namespace) -> int:
    if cursor.get("schema_version") != 1:
        raise ValueError("dual-MTF cursor schema_version must equal 1")
    if cursor.get("execution_authority") != "none":
        raise ValueError("dual-MTF cursor execution authority is invalid")
    if cursor.get("runtime_strategy_changed") is not False:
        raise ValueError("dual-MTF cursor strategy-change flag is invalid")
    _require_identity(cursor, args, "cursor")
    _validate_cursor_artifact(cursor)
    return _nonnegative_int(cursor.get("analyzed_closed_trades"), "cursor count")


def _validate_cursor_artifact(cursor: Record) -> None:
    artifact = _mapping(cursor.get("artifact"), "cursor artifact")
    path_value = artifact.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("cursor artifact path must be non-empty text")
    path = Path(path_value)
    raw = path.read_bytes()
    expected_bytes = _nonnegative_int(artifact.get("bytes"), "cursor artifact bytes")
    if len(raw) != expected_bytes:
        raise ValueError("cursor artifact byte count does not match")
    if artifact.get("sha256") != sha256(raw).hexdigest():
        raise ValueError("cursor artifact SHA-256 does not match")


def _cursor_payload(
    args: argparse.Namespace,
    closed: int,
    artifact: Path,
) -> dict[str, object]:
    raw = artifact.read_bytes()
    return {
        "schema_version": 1,
        "mode": "v39_dual_mtf_reversal_close_monitor_v1",
        "run_id": args.run_id,
        "profile_fingerprint": args.profile_fingerprint,
        "analyzed_closed_trades": closed,
        "artifact": {
            "path": str(artifact.resolve()),
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def _publish_subprocess(args: argparse.Namespace, output: Path) -> None:
    command = [
        sys.executable,
        str(args.challenger_script),
        "--ledger-root",
        str(args.ledger_root),
        "--run-id",
        args.run_id,
        "--profile-fingerprint",
        args.profile_fingerprint,
        "--out",
        str(output),
        "--persistence-decisions",
        "1",
        "3",
        "5",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout)[-1000:].strip()
        raise RuntimeError(f"dual-MTF challenger failed: {detail}")


def _artifact_path(directory: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return directory / f"v39_dual_mtf_profit_reversal_exit_{stamp}_forward.json"


def _validate_args(args: argparse.Namespace) -> None:
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0.0:
        raise ValueError("dual-MTF monitor interval must be finite and positive")
    if args.max_cycles < 0:
        raise ValueError("dual-MTF monitor max cycles cannot be negative")
    if not args.run_id.strip() or not args.profile_fingerprint.strip():
        raise ValueError("dual-MTF monitor identities must be non-empty")
    inputs = {args.checkpoint.resolve(), args.bootstrap_artifact.resolve()}
    if args.cursor.resolve() in inputs:
        raise ValueError("dual-MTF cursor must differ from evidence inputs")


def _require_identity(row: Record, args: argparse.Namespace, label: str) -> None:
    run_id = row.get("run_id")
    profile = row.get("profile_fingerprint")
    if run_id != args.run_id:
        raise ValueError(f"{label} run identity does not match")
    if profile != args.profile_fingerprint:
        raise ValueError(f"{label} profile identity does not match")


def _read_mapping(path: Path, label: str) -> Record:
    return _mapping(json.loads(path.read_bytes()), label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise TypeError(f"{label} must be a list of objects")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _result(state: str, closed: int, cursor: Record) -> dict[str, object]:
    return {
        "state": state,
        "closed_trades": closed,
        "cursor": dict(cursor),
        "execution_authority": "none",
    }


def _emit(state: str, **fields: object) -> None:
    stream = sys.stderr if state == "unavailable" else sys.stdout
    print(
        json.dumps(
            {"event": "v39_dual_mtf_exit_monitor", "state": state, **fields},
            sort_keys=True,
        ),
        file=stream,
        flush=True,
    )


_EXPECTED_FAILURES = (
    json.JSONDecodeError,
    OSError,
    RuntimeError,
    subprocess.SubprocessError,
    TypeError,
    ValueError,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the close-triggered, authority-none monitor."""
    return run_monitor(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
