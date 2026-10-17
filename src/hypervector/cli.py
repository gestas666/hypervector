"""Unified CLI entry point; engine imports belong to dispatched services."""

from __future__ import annotations

import argparse
import json
import os
import sys

from hypervector.commands.common import CommandRefused
from hypervector.commands.registry import (
    CLI_COMMANDS as CLI_COMMANDS,
    LEGACY_ALIASES as LEGACY_ALIASES,
    RETIRED as RETIRED,
    build_parser as build_parser,
    spec_for,
)

MODEL_ENVIRONMENT = frozenset(
    {"HYPERVECTOR_METALABEL_ROOT", "HYPERVECTOR_IMPULSE_BTC_ROOT"}
)
OXA_ENVIRONMENT = frozenset({"OXA_API_KEY"})


def load_command_environment(args: argparse.Namespace) -> None:
    """Load only the dotenv names the selected spec declares.

    The full dotenv (including the signing key) loads only for a spec that declares
    ``live-credentials`` and only when both authority flags were given.
    """
    from hypervector.runtime_env import (
        load_dotenv_if_present,
        load_selected_env_if_present,
    )

    declared = spec_for(args.command).get("environment", [])
    if "live-credentials" in declared:
        if getattr(args, "enabled", False) and getattr(
            args, "i_accept_live_risk", False
        ):
            load_dotenv_if_present()
    if "oxa" in declared:
        load_selected_env_if_present(OXA_ENVIRONMENT)
    if "models" in declared:
        load_selected_env_if_present(MODEL_ENVIRONMENT)


def _error(args: argparse.Namespace, exc: BaseException, code: int) -> int:
    """Print the single JSON error document on stderr and return its exit code."""
    report = {
        "ok": False,
        "command": getattr(args, "command", None),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    print(json.dumps(report), file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    """Parse, load the declared environment, dispatch, and map failures to exit codes."""
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if argv is None:
            load_command_environment(args)
        return int(args.func(args))
    except CommandRefused as exc:
        return _error(args, exc, 2)
    except KeyboardInterrupt:
        return 130
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        if os.environ.get("HYPERVECTOR_DEBUG") == "1":
            raise
        return _error(args, exc, 1)


if __name__ == "__main__":
    raise SystemExit(main())
