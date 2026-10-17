"""Unified CLI entry point; engine imports belong to dispatched services."""

from __future__ import annotations

from importlib import import_module
from importlib.resources import files
import json
import argparse
import sys

from hypervector.commands.registry import CLI_COMMANDS as CLI_COMMANDS, build_parser
from hypervector.config import FLOOR_LOOKBACK, PROMO_LOOKBACK


def _load_dotenv_if_present() -> None:
    """Load operator credentials only for explicitly invoked execution commands."""
    from hypervector.runtime_env import load_dotenv_if_present

    load_dotenv_if_present()


def __getattr__(name: str) -> object:
    """Keep existing Python helper imports available during the CLI migration."""
    owners = json.loads(
        files("hypervector.commands").joinpath("compat.json").read_text()
    )
    if name not in owners:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"hypervector.commands.{owners[name]}"), name)


def _load_command_environment(args: argparse.Namespace) -> None:
    """Keep archive/model dotenv support without loading signing keys for observers."""
    from hypervector.runtime_env import load_selected_env_if_present

    if args.command in {"live-run", "cohort-live"}:
        if args.enabled and args.i_accept_live_risk:
            _load_dotenv_if_present()
    elif args.command.startswith("oxa-"):
        load_selected_env_if_present(frozenset({"OXA_API_KEY"}))
    elif args.command in {"paper-run", "hypervelocity-shadow-run"}:
        load_selected_env_if_present(
            frozenset({"HYPERVECTOR_METALABEL_ROOT", "HYPERVECTOR_IMPULSE_BTC_ROOT"})
        )


def main(argv: list[str] | None = None) -> int:
    """Dispatch a scoped workflow without creating clients during discovery."""
    parser = build_parser()
    values = sys.argv[1:] if argv is None else argv
    if any(value in {"cohort-tui", "hypervelocity-tui"} for value in values):
        parser.error(
            "the TUI has been retired; use 'cohort observe', 'cohort checkpoint', "
            "or 'paper shadow-run'; live execution uses 'cohort live' with both authority flags"
        )
    args = parser.parse_args(values)
    if argv is None:
        _load_command_environment(args)
    if getattr(args, "lookback", None) is not None and args.lookback < FLOOR_LOOKBACK:
        print(
            f"lookback must be >= {FLOOR_LOOKBACK} (promo={PROMO_LOOKBACK})",
            file=sys.stderr,
        )
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
