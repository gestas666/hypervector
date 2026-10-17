"""Transport for packaged operational services: argv, preflight and process replacement.

Operation-backed commands replace the CLI process with ``python -m <module>`` so
signals, exit codes and supervision see the service itself. ``_exec`` is the test
seam; the test suite replaces it with a function that raises.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import os
import sys

from hypervector.commands.common import CommandRefused
from hypervector.commands.registry import (
    Handler,
    argument_dest,
    iter_arguments,
    spec_for,
)

_exec = os.execv


def _transport(flag: str, action: object, value: object) -> Iterable[str]:
    """Serialize one parsed value in the module's own spelling."""
    if action == "store_true":
        return (flag,) if value is True else ()
    if action == "store_false":
        return (flag,) if value is False else ()
    if action == "boolean_optional":
        if value is None:
            return ()
        return (flag,) if value else ("--no-" + flag[2:],)
    if value is None:
        return ()
    items = value if action == "append" else [value]
    return tuple(part for item in items for part in (flag, str(item)))  # type: ignore[union-attr]


def operation_argv(args: argparse.Namespace) -> tuple[str, ...]:
    """The exact service argv for a parsed operation command (no shell parsing)."""
    spec = spec_for(args.command)
    command = [sys.executable, "-m", str(spec["operation"])]
    for argument in iter_arguments(spec):
        flag = argument.get("transport", argument["flags"][0])
        if flag is False or argument.get("hidden"):
            continue
        value = getattr(args, argument_dest(argument), None)
        command.extend(_transport(str(flag), argument["options"].get("action"), value))
    return tuple(command)


def replace_process(command: tuple[str, ...]) -> int:
    """Flush output and replace this process with the service."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        _exec(command[0], list(command))
    except OSError as exc:
        print(f"could not start {command[2]}: {exc}", file=sys.stderr)
        return 2
    return 0


def run_operation(args: argparse.Namespace) -> int:
    """Check authority and preflight, then exec the declared service module."""
    spec = spec_for(args.command)
    if spec.get("authority") == "live" and not (
        getattr(args, "enabled", False) and getattr(args, "i_accept_live_risk", False)
    ):
        raise CommandRefused(
            f"{args.command} requires both --enabled and --i-accept-live-risk"
        )
    if spec.get("preflight"):
        Handler(str(spec["preflight"]))(args)
    return replace_process(operation_argv(args))
