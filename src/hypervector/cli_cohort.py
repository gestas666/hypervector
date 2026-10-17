"""Fail-closed, installable transport for shared portfolio operations."""

from __future__ import annotations

import argparse
import subprocess
import sys

from hypervector.commands.operations import operation_command
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.cohort_process_commands import require_live_provider_dependencies


def cohort_command(args: argparse.Namespace) -> tuple[str, ...]:
    """Resolve exact operational options while preserving explicit live authority."""
    if args.command == "cohort-live" and not (args.enabled and args.i_accept_live_risk):
        raise ValueError("live cohort requires both --enabled and --i-accept-live-risk")
    return operation_command(args)


def run_cohort_command(args: argparse.Namespace) -> int:
    """Execute the resolved project script and propagate its return code."""
    try:
        command = cohort_command(args)
        if args.command == "cohort-live":
            if args.config is None:
                raise ValueError("select an explicit --config for live execution")
            config = load_multi_asset_live_config(args.config, mode="observe")
            require_live_provider_dependencies(config)
    except ValueError as exc:
        print(f"{args.command} refused: {exc}", file=sys.stderr)
        return 2
    return subprocess.run(command, check=False).returncode
