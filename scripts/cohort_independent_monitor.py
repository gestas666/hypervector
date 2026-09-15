"""Start a separate read-only monitor without controlling an existing backend."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import math
from pathlib import Path
import sys
import time

from hypervector.live.cohort_accounting_rollover import load_required_accounting_epoch
from hypervector.live.cohort_independent_monitor import run_independent_monitor
from hypervector.live.cohort_tui_commands import CHECKPOINT_OUTPUT
from hypervector.live.cohort_tui_launch_options import build_parser as launch_parser
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.process_signal_stop import install_process_signal_stop
from hypervector.research.cohort_independent_checkpoint import publish_independent_checkpoint
from hypervector.runtime_lock import RuntimeLockError, cohort_checkpoint_runtime_lock
from scripts.multi_asset_bidirectional_canary_tui import resolve_launch


def build_parser() -> argparse.ArgumentParser:
    """Reuse monitor options with internal worker-only checkpoint arguments."""
    parser = launch_parser()
    parser.set_defaults(mode="monitor")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-checkpoint", type=Path, default=CHECKPOINT_OUTPUT, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-id", help=argparse.SUPPRESS)
    parser.add_argument("--interval-seconds", type=float, default=30.0, help=argparse.SUPPRESS)
    return parser


def run_worker(args: argparse.Namespace) -> int:
    """Publish same-run native reports while sharing only external observer data."""
    if args.out is None or not args.run_id:
        raise ValueError("independent reporter requires --out and --run-id")
    if not math.isfinite(args.interval_seconds) or args.interval_seconds <= 0:
        raise ValueError("independent reporter interval must be positive and finite")
    config = load_multi_asset_live_config(args.config, mode="observe")
    epoch = load_required_accounting_epoch(args.accounting_epoch_bundle, config)
    with cohort_checkpoint_runtime_lock(args.out):
        while True:
            result = publish_independent_checkpoint(
                source_path=args.source_checkpoint, destination=args.out,
                config=config, run_id=args.run_id, accounting_epoch=epoch,
            )
            print(json.dumps({"event": "cohort_independent_checkpoint", "run_id": args.run_id,
                              "generated_at_utc": result["generated_at_utc"],
                              "execution_authority": "none"}), flush=True)
            time.sleep(args.interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    """Reject execution authority and supervise only independent monitoring."""
    args = build_parser().parse_args(argv)
    try:
        if args.mode != "monitor" or args.enabled or args.i_accept_live_risk or args.resume_transition_drain:
            raise ValueError("independent monitor requires monitor mode without execution flags")
        if args.config is None:
            raise ValueError("independent monitor requires the active --config")
        if args.worker:
            return run_worker(args)
        if args.out is not None or args.run_id is not None or args.staged_config is not None:
            raise ValueError("independent monitor uses the active profile and its own output")
        launch = resolve_launch(args, credentials_present=False)
        return run_independent_monitor(
            launch, source_path=args.source_checkpoint, stop=install_process_signal_stop(),
        )
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, RuntimeLockError, ValueError) as exc:
        print(f"independent monitor failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
