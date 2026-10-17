"""Generated minimal argv for packaged CLI specs, shared by the CLI surface tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from hypervector.commands.registry import iter_arguments, spec_for

WINDOW = {"--start": "2026-01-01T00:00:00Z", "--end": "2026-01-02T00:00:00Z"}
SAMPLES = {
    "int": "2",
    "float": "1.5",
    "lookback_days": "30",
    "page_limit": "10",
    "utc_datetime": "2026-01-01T00:00:00Z",
    "fee_model": "hl_maker",
    "sampler": "optuna",
    "Path": "sample.path",
}


def sample_value(argument: dict[str, Any]) -> str:
    """A valid command-line value for one argument declaration."""
    options = argument["options"]
    flag = argument["flags"][0]
    if flag in WINDOW:
        return WINDOW[flag]
    if options.get("choices"):
        return str(options["choices"][0])
    return SAMPLES.get(str(options.get("type")), "sample")


def minimal_argv(spec: dict[str, Any], skip: Iterable[str] = ()) -> list[str]:
    """Required options (and one member of each required group) with sample values."""
    skipped = set(skip)
    required_groups = {
        index
        for index, group in enumerate(spec.get("exclusive_groups", []))
        if group.get("required")
    }
    argv: list[str] = []
    for argument in iter_arguments(spec):
        flag = argument["flags"][0]
        if flag in skipped or argument.get("hidden") or not flag.startswith("-"):
            continue
        group = argument.get("exclusive_group")
        if group in required_groups:
            required_groups.discard(group)
            argv += [flag, sample_value(argument)]
        elif argument.get("required"):
            argv += [flag, sample_value(argument)]
    return argv


def command_argv(command: str, skip: Iterable[str] = ()) -> list[str]:
    """Canonical words plus minimal options for one "group action" command."""
    return [*command.split(), *minimal_argv(spec_for(command), skip)]
