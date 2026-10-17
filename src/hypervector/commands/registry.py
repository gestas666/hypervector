"""Engine-independent command registry: specs, legacy names, parsers and post-parse rules.

Everything here reads packaged JSON only, so help, status and argument errors never
import an engine. Specs live under ``specs/<group>/<action>.json`` (schema 2).
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib import import_module
from importlib.resources import files
import json
from pathlib import Path
import sys
from typing import Any, Callable, cast

from hypervector.config import FLOOR_LOOKBACK, PROMO_LOOKBACK

Spec = dict[str, Any]
RESERVED_DESTS = frozenset({"command", "group", "action", "func", "data_root"})
OPERATION_HANDLER = "hypervector.commands.operations:run_operation"
_ROOT_DESCRIPTION = (
    "Unified Hyperliquid research and execution: VectorBT, NautilusTrader, Karpathy "
    "autotuning, 0xArchive and paper/shadow trading. Live execution requires explicit "
    "authority (--enabled --i-accept-live-risk)."
)


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


@dataclass(frozen=True)
class Legacy:
    """An old command spelling rewritten to a canonical command before parsing."""

    words: tuple[str, str]
    insert: tuple[str, ...] = ()


class RetiredCommand(Exception):
    """An old command name that no longer exists; the message names the replacement."""


# --- converters -------------------------------------------------------------


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


def lookback_days(value: str) -> int:
    """Calendar-day lookbacks below the research floor are usage errors."""
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid day count: {value!r}") from exc
    if days < FLOOR_LOOKBACK:
        raise argparse.ArgumentTypeError(
            f"lookback must be >= {FLOOR_LOOKBACK} days (promo={PROMO_LOOKBACK})"
        )
    return days


def fee_model(value: str) -> str:
    """Normalize a fee preset or alias to its canonical name; unknown names exit 2."""
    names, aliases = fee_model_table()
    key = str(value).lower().strip().replace("-", "_")
    key = aliases.get(key, key)
    if key not in names:
        raise argparse.ArgumentTypeError(
            f"unknown fee model {value!r}; choose one of {', '.join(names)}"
        )
    return key


def sampler(value: str) -> str:
    """Accept the retired 'hybrid' sampler name as Optuna, with a note."""
    key = str(value).lower().strip()
    if key == "hybrid":
        print("note: --sampler hybrid is now --sampler optuna", file=sys.stderr)
        return "optuna"
    if key not in ("karpathy", "optuna"):
        raise argparse.ArgumentTypeError(
            f"unknown sampler {value!r}; choose karpathy or optuna"
        )
    return key


CONVERTERS: dict[str, Callable[[str], object]] = {
    "int": int,
    "float": float,
    "Path": Path,
    "utc_datetime": parse_utc_datetime,
    "page_limit": bounded_page_limit,
    "lookback_days": lookback_days,
    "fee_model": fee_model,
    "sampler": sampler,
}


# --- packaged inventory -----------------------------------------------------


@lru_cache(maxsize=None)
def _resource(*parts: str) -> Any:
    """Read one packaged JSON document."""
    return json.loads(files(__package__).joinpath(*parts).read_text(encoding="utf-8"))


def groups() -> Spec:
    """Group order, help, sections, default actions and legacy group names."""
    return cast(Spec, _resource("groups.json"))


def retired() -> dict[str, str]:
    """Old command words that now exit 2 with a message naming the replacement."""
    return cast(dict[str, str], _resource("retired.json"))


def fragment(name: str) -> Spec:
    """One shared argument fragment."""
    return cast(Spec, _resource("specs", "_fragments", f"{name}.json"))


@lru_cache(maxsize=1)
def fee_model_table() -> tuple[tuple[str, ...], dict[str, str]]:
    """Canonical fee preset names and value aliases, kept in the fees fragment."""
    fees = fragment("fees")
    return tuple(fees["fee_model_names"]), dict(fees["fee_model_aliases"])


@lru_cache(maxsize=1)
def command_specs() -> tuple[tuple[str, str, Spec], ...]:
    """(group, action, expanded spec) for every packaged command, in help order."""
    result = []
    root = files(__package__).joinpath("specs")
    for group in groups()["order"]:
        directory = root.joinpath(group)
        if not directory.is_dir():
            continue
        for resource in sorted(
            directory.iterdir(), key=lambda item: item.name.removesuffix(".json")
        ):
            if resource.name.endswith(".json"):
                spec = json.loads(resource.read_text(encoding="utf-8"))
                action = resource.name.removesuffix(".json")
                result.append((group, action, _expand(spec, f"{group} {action}")))
    return tuple(result)


def _expand(spec: Spec, command: str) -> Spec:
    """Insert fragment arguments after the spec's own arguments."""
    if spec.get("schema") != 2:
        raise ValueError(f"{command}: CLI spec schema must be 2")
    overrides = dict(spec.get("fragment_overrides", {}))
    arguments = list(spec.get("arguments", []))
    for name in spec.get("include", []):
        for argument in fragment(name)["arguments"]:
            arguments.append(
                _override(argument, overrides.pop(argument["flags"][0], None))
            )
    if overrides:
        raise ValueError(
            f"{command}: overrides for unknown fragment flags {sorted(overrides)}"
        )
    return {**spec, "arguments": arguments}


def _override(argument: Spec, override: Spec | None) -> Spec:
    """Apply a spec's allowed per-command change to one fragment argument."""
    if not override:
        return argument
    result = {**argument, "options": dict(argument["options"])}
    for key, value in override.items():
        if key == "required":
            result["required"] = bool(value)
        elif key in ("default", "help", "choices"):
            result["options"][key] = value
        else:
            raise ValueError(f"fragment override may not change {key!r}")
    return result


def _command_index() -> dict[str, Spec]:
    return {f"{group} {action}": spec for group, action, spec in command_specs()}


def spec_for(command_id: str) -> Spec:
    """The expanded spec of one canonical "group action" command."""
    return _SPECS_BY_ID[command_id]


def argument_dest(argument: Spec) -> str:
    """The namespace attribute an argument writes."""
    dest = argument["options"].get("dest")
    return (
        str(dest) if dest else str(argument["flags"][0]).lstrip("-").replace("-", "_")
    )


def iter_arguments(spec: Spec) -> Iterator[Spec]:
    """Every argument of an expanded spec, including hidden compatibility ones."""
    yield from spec["arguments"]


def visible_flags(spec: Spec) -> Iterator[tuple[str, Spec]]:
    """Canonical (visible) option spellings with their argument declarations."""
    for argument in iter_arguments(spec):
        if not argument.get("hidden"):
            for flag in argument["flags"]:
                if flag.startswith("-"):
                    yield flag, argument


def _legacy_table() -> dict[str, Legacy]:
    table: dict[str, Legacy] = {}
    for group, action, spec in command_specs():
        for entry in spec.get("legacy", []):
            words = entry if isinstance(entry, str) else entry["words"]
            insert = () if isinstance(entry, str) else tuple(entry.get("insert", ()))
            if words in table:
                raise ValueError(f"duplicate legacy command name: {words!r}")
            table[words] = Legacy((group, action), insert)
    return table


_SPECS_BY_ID = _command_index()
GROUP_ORDER: tuple[str, ...] = tuple(groups()["order"])
ACTIONS: dict[str, tuple[str, ...]] = {
    group: tuple(action for owner, action, _ in command_specs() if owner == group)
    for group in GROUP_ORDER
    if any(owner == group for owner, _, _ in command_specs())
}
CLI_COMMANDS: tuple[str, ...] = tuple(_SPECS_BY_ID)
LEGACY_ALIASES: dict[str, Legacy] = _legacy_table()
RETIRED: dict[str, str] = retired()
LEGACY_GROUPS: frozenset[str] = frozenset(groups()["legacy_groups"])
DEFAULT_ACTION: dict[str, str] = {
    group: str(meta["default_action"])
    for group, meta in groups()["groups"].items()
    if "default_action" in meta
}


# --- argv normalization ------------------------------------------------------


def _skip_data_root(argv: Sequence[str], index: int) -> int:
    while argv[index : index + 1] and (
        argv[index] == "--data-root" or argv[index].startswith("--data-root=")
    ):
        index += 2 if argv[index] == "--data-root" else 1
    return index


def _rewrite(argv: list[str], i: int, j: int, legacy: Legacy) -> list[str]:
    return [*argv[:i], *legacy.words, *argv[i + 1 : j], *legacy.insert, *argv[j + 1 :]]


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """Rewrite leading legacy command words to canonical ones; option values are untouched."""
    argv = list(argv)
    i = _skip_data_root(argv, 0)
    if i >= len(argv) or argv[i].startswith("-"):
        return argv
    first = argv[i]
    j = _skip_data_root(argv, i + 1)
    second = argv[j] if j < len(argv) else None
    if first in ACTIONS:
        if second is None or second in ("-h", "--help") or second in ACTIONS[first]:
            return argv
        key = f"{first} {second}"
        if key in RETIRED:
            raise RetiredCommand(RETIRED[key])
        if key in LEGACY_ALIASES:
            return _rewrite(argv, i, j, LEGACY_ALIASES[key])
        if second.startswith("-") and first in DEFAULT_ACTION:
            return [*argv[:i], first, DEFAULT_ACTION[first], *argv[i + 1 :]]
        return argv
    if first in LEGACY_GROUPS:
        key = f"{first} {second}"
        if key in RETIRED:
            raise RetiredCommand(RETIRED[key])
        if key in LEGACY_ALIASES:
            return _rewrite(argv, i, j, LEGACY_ALIASES[key])
        raise RetiredCommand(RETIRED[first])
    if first in RETIRED:
        raise RetiredCommand(RETIRED[first])
    if first in LEGACY_ALIASES:
        return _rewrite(argv, i, i, LEGACY_ALIASES[first])
    return argv


# --- parsers -----------------------------------------------------------------


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep epilog layout and state non-trivial defaults."""

    def _get_help_string(self, action: argparse.Action) -> str | None:
        text = action.help or ""
        default = action.default
        if (
            not action.option_strings
            or "default" in text.lower()
            or default is None
            or default is False
            or default is argparse.SUPPRESS
            or default == []
        ):
            return action.help
        return f"{text} (default: %(default)s)"


class CommandParser(argparse.ArgumentParser):
    """Group and command parser: shared formatter, no option abbreviations."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", HelpFormatter)
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)


class HypervectorParser(CommandParser):
    """Root parser: normalizes legacy argv, then enforces spec rules after parsing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._commands: dict[str, tuple[argparse.ArgumentParser, Spec]] = {}

    def register_command(
        self, command: str, parser: argparse.ArgumentParser, spec: Spec
    ) -> None:
        """Remember a command parser for post-parse errors."""
        self._commands[command] = (parser, spec)

    def parse_known_args(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[argparse.Namespace, list[str]]:
        """Rewrite legacy names, parse, then apply required/data-root rules."""
        argv = list(sys.argv[1:] if args is None else args)
        try:
            argv = normalize_argv(argv)
        except RetiredCommand as exc:
            self.exit(2, f"{self.prog}: {exc}\n")
        parsed, extras = super().parse_known_args(argv, namespace)
        self._post_parse(parsed)
        return parsed, extras

    def _post_parse(self, ns: argparse.Namespace) -> None:
        entry = self._commands.get(getattr(ns, "command", ""))
        if entry is None:
            return
        parser, spec = entry
        missing = [
            "/".join(argument["flags"])
            for argument in iter_arguments(spec)
            if argument.get("required")
            and getattr(ns, argument_dest(argument), None) is None
        ]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
        _refuse_data_root(parser, spec, ns)
        _fill_data_defaults(spec, ns)


def _refuse_data_root(
    parser: argparse.ArgumentParser, spec: Spec, ns: argparse.Namespace
) -> None:
    if spec.get("data_root") != "refused":
        return
    if Path(ns.data_root).resolve() != Path("data").resolve():
        reason = spec.get("data_root_reason", "its paths are fixed")
        parser.error(f"--data-root is not supported by '{ns.command}': {reason}")


def _fill_data_defaults(spec: Spec, ns: argparse.Namespace) -> None:
    for argument in iter_arguments(spec):
        relative = argument.get("data_default")
        dest = argument_dest(argument)
        if relative and getattr(ns, dest, None) is None:
            value = Path(ns.data_root) / str(relative)
            as_path = argument["options"].get("type") == "Path"
            setattr(ns, dest, value if as_path else str(value))


def add_data_root(parser: argparse.ArgumentParser, *, root: bool = False) -> None:
    """Allow explicit data scoping before or after group and command names."""
    parser.add_argument(
        "--data-root",
        default="data" if root else argparse.SUPPRESS,
        help="data directory (default: ./data)",
    )


_VALUELESS_ACTIONS = frozenset({"store_true", "store_false", "boolean_optional"})


def _argparse_options(argument: Spec) -> dict[str, Any]:
    options = dict(argument["options"])
    spelled = str(argument["flags"][0]).lstrip("-").replace("-", "_")
    if (
        str(argument["flags"][0]).startswith("-")
        and options.get("dest", spelled) != spelled
        and options.get("action") not in _VALUELESS_ACTIONS
        and "choices" not in options
    ):
        options.setdefault("metavar", spelled.upper())
    if "type" in options:
        options["type"] = CONVERTERS[options["type"]]
    if options.get("action") == "boolean_optional":
        options["action"] = argparse.BooleanOptionalAction
    if argument.get("required") and options.get("help"):
        options["help"] = f"{options['help']} (required)"
    if argument.get("hidden"):
        options.update(help=argparse.SUPPRESS, default=argparse.SUPPRESS)
    return options


def configure_command(parser: argparse.ArgumentParser, spec: Spec) -> None:
    """Add a spec's canonical options plus hidden legacy spellings."""
    exclusive = [
        parser.add_mutually_exclusive_group(**group)
        for group in spec.get("exclusive_groups", [])
    ]
    for argument in iter_arguments(spec):
        target: Any = (
            exclusive[argument["exclusive_group"]]
            if "exclusive_group" in argument
            else parser
        )
        options = _argparse_options(argument)
        target.add_argument(*argument["flags"], **options)
        if argument.get("legacy_flags"):
            hidden = {
                **options,
                "help": argparse.SUPPRESS,
                "default": argparse.SUPPRESS,
            }
            target.add_argument(*argument["legacy_flags"], **hidden)


def _handler_target(spec: Spec) -> str:
    if spec["kind"] == "operation":
        return str(spec.get("handler", OPERATION_HANDLER))
    return str(spec["handler"])


def _rows(lines: list[tuple[str, str]], width: int = 0) -> list[str]:
    width = max([width, *(len(name) + 2 for name, _ in lines)])
    return [f"  {name:<{width}}{text}" for name, text in lines]


def _root_epilog() -> str:
    meta = groups()["groups"]
    shortcuts = groups()["shortcuts"]
    width = max(len(name) for name in [*ACTIONS, *shortcuts]) + 2
    lines: list[str] = []
    for title, pillar in (("pillars", True), ("supporting", False)):
        chosen = [
            (group, meta[group]["help"])
            for group in GROUP_ORDER
            if group in ACTIONS and bool(meta[group].get("pillar")) is pillar
        ]
        lines += [f"{title}:", *_rows(chosen, width), ""]
    rows = [(word, f"same as '{target}'") for word, target in shortcuts.items()]
    lines += ["shortcuts:", *_rows(rows, width), ""]
    lines.append("Run 'hypervector <group> --help' to list a group's commands.")
    return "\n".join(lines)


def _group_epilog(group: str) -> str:
    rows = [(action, spec) for owner, action, spec in command_specs() if owner == group]
    width = max(len(action) for action, _ in rows) + 2
    sections = groups()["groups"][group].get("sections")
    if not sections:
        return "\n".join(
            ["commands:", *_rows([(a, s["help"]) for a, s in rows], width)]
        )
    blocks = []
    for key, title in sections.items():
        chosen = [(a, s["help"]) for a, s in rows if s.get("section") == key]
        if chosen:
            blocks.append("\n".join([f"{key} ({title}):", *_rows(chosen, width)]))
    return "\n\n".join(blocks)


def _add_groups(
    parser: HypervectorParser,
) -> dict[str, argparse._SubParsersAction[CommandParser]]:
    sub = parser.add_subparsers(
        dest="group",
        required=True,
        metavar="<group>",
        help="command group (listed below)",
        parser_class=CommandParser,
    )
    children = {}
    for group in GROUP_ORDER:
        if group not in ACTIONS:
            continue
        text = groups()["groups"][group]["help"]
        group_parser = sub.add_parser(
            group, description=text, epilog=_group_epilog(group)
        )
        add_data_root(group_parser)
        children[group] = group_parser.add_subparsers(
            dest="action",
            required=True,
            metavar="<action>",
            help="command (listed below)",
            parser_class=CommandParser,
        )
    return children


def build_parser() -> HypervectorParser:
    """Build canonical group/command parsers; old names are rewritten, never built."""
    parser = HypervectorParser(
        prog="hypervector", description=_ROOT_DESCRIPTION, epilog=_root_epilog()
    )
    add_data_root(parser, root=True)
    children = _add_groups(parser)
    for group, action, spec in command_specs():
        child = children[group].add_parser(
            action, description=spec.get("description") or spec["help"]
        )
        add_data_root(child)
        configure_command(child, spec)
        command = f"{group} {action}"
        child.set_defaults(
            command=command,
            group=group,
            action=action,
            func=Handler(_handler_target(spec)),
        )
        parser.register_command(command, child, spec)
    return parser
