"""One engine-independent command inventory shared by help and dispatch."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib import import_module
from importlib.resources import files
import json
from pathlib import Path
from typing import Callable, cast

GROUPS = {
    "system": "Local layout, capabilities and diagnostics",
    "data": "Hyperliquid history, funding and orderbook recording",
    "archive": "Bounded Hyperliquid evidence from 0xArchive",
    "research": "VectorBT backtests, Karpathy tuning, exports and DuckDB",
    "nautilus": "Event-driven historical validation of strategy exports",
    "paper": "Paper and shadow sessions, reports and recoverable reset",
    "live": "Explicitly armed Hyperliquid execution and reports",
    "cohort": "Shared portfolio operation, observation and audits",
    "regime": "Causal classification, evaluation and telemetry export",
    "model": "Walk-forward metalabel training",
}


@dataclass(frozen=True)
class Handler:
    """Resolve a service only when its command is executed."""

    target: str

    def __call__(self, args: argparse.Namespace) -> int:
        """Import and execute the registered namespace handler."""
        module, name = self.target.split(":", 1)
        function = cast(
            Callable[[argparse.Namespace], int], getattr(import_module(module), name)
        )
        return function(args)


def parse_utc_datetime(value: str) -> datetime:
    """Require a timezone-aware ISO timestamp and normalize it to UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid ISO-8601 timestamp: {value}"
        ) from exc
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset or Z")
    return parsed.astimezone(UTC)


def bounded_page_limit(value: str) -> int:
    """Reject archive page sizes outside the supported API contract."""
    limit = int(value)
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("limit must be between 1 and 1000")
    return limit


@lru_cache(maxsize=1)
def command_specs() -> tuple[tuple[str, dict[str, object]], ...]:
    """Read packaged declarative options without importing any engine."""
    result = []
    for group in GROUPS:
        directory = files(__package__).joinpath("specs", group)
        for resource in sorted(directory.iterdir(), key=lambda item: item.name):
            value: object = json.loads(resource.read_text())
            if not isinstance(value, dict):
                raise ValueError(f"invalid packaged CLI inventory: {resource.name}")
            result.append((group, value))
    return tuple(result)


CLI_COMMANDS = tuple(str(spec["name"]) for _, spec in command_specs())


def configure_command(parser: argparse.ArgumentParser, spec: dict[str, object]) -> None:
    """Apply one option contract to its focused name or compatibility alias."""
    exclusive = [
        parser.add_mutually_exclusive_group(**group)
        for group in spec.get("exclusive_groups", [])
    ]
    converters = {
        "int": int,
        "float": float,
        "Path": Path,
        "_parse_utc_datetime": parse_utc_datetime,
        "_bounded_page_limit": bounded_page_limit,
    }
    for argument in spec["arguments"]:
        options = dict(argument["options"])
        if "type" in options:
            options["type"] = converters[options["type"]]
        if options.get("action") == "boolean_optional":
            options["action"] = argparse.BooleanOptionalAction
        target = (
            exclusive[argument["exclusive_group"]]
            if "exclusive_group" in argument
            else parser
        )
        target.add_argument(*argument["flags"], **options)
    parser.set_defaults(command=spec["name"], func=Handler(str(spec["handler"])))


def add_data_root(parser: argparse.ArgumentParser, *, root: bool = False) -> None:
    """Allow explicit data scoping before or after command group names."""
    parser.add_argument(
        "--data-root",
        default="data" if root else argparse.SUPPRESS,
        help="data directory (default: ./data)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build focused workflows and backward-compatible non-visual aliases."""
    parser = argparse.ArgumentParser(
        prog="hypervector",
        description=(
            "Unified Hyperliquid research and execution: VectorBT, NautilusTrader, "
            "Karpathy autotuning, 0xArchive and paper/shadow trading. Live execution "
            "requires explicit authority."
        ),
        epilog="Use 'hypervector <group> --help' to explore a workflow.",
    )
    add_data_root(parser, root=True)
    sub = parser.add_subparsers(
        dest="command", required=True, metavar="{" + ",".join(GROUPS) + "}"
    )
    grouped = {}
    for group, help_text in GROUPS.items():
        parent = sub.add_parser(group, help=help_text, description=help_text)
        add_data_root(parent)
        grouped[group] = (
            parent,
            parent.add_subparsers(dest="group", required=group != "regime"),
        )
    for group, spec in command_specs():
        parent, children = grouped[group]
        child = children.add_parser(str(spec["action"]), help=str(spec["help"]))
        add_data_root(child)
        configure_command(child, spec)
        if spec["name"] == group:
            configure_command(parent, spec)
        else:
            alias = sub.add_parser(str(spec["name"]))
            add_data_root(alias)
            configure_command(alias, spec)
    return parser
