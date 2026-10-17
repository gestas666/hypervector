"""Namespace transport for packaged headless operational entry points."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from hypervector.commands.registry import command_specs


def operation_command(args: argparse.Namespace) -> tuple[str, ...]:
    """Serialize the selected service's declared options without shell parsing."""
    spec = next(spec for _, spec in command_specs() if spec["name"] == args.command)
    command = [sys.executable, "-m", f"hypervector.operations.{spec['operation']}"]
    for argument in spec["arguments"]:
        options = argument["options"]
        value = getattr(args, options["dest"])
        if (
            spec["operation"] == "multi_asset_bidirectional_observe"
            and options["dest"] == "ledger_root"
            and value is None
        ):
            value = Path(args.data_root) / "paper" / "cohort"
        flag = argument["flags"][0]
        action = options.get("action")
        if action in {"store_true", "store_false"}:
            if value is (action == "store_true"):
                command.append(flag)
        elif action == "boolean_optional":
            if value is not None:
                command.append(flag if value else "--no-" + flag[2:])
        elif value is not None:
            for item in value if action == "append" else [value]:
                command.extend((flag, str(item)))
    return tuple(command)


def run_operation(args: argparse.Namespace) -> int:
    """Run the service in its own process and propagate its result."""
    return subprocess.run(operation_command(args), check=False).returncode
