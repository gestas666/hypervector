"""Lint for the declarative CLI specs (schema 2) and their registry tables."""

from __future__ import annotations

from collections import defaultdict
from importlib.resources import files
import json
import re

import pytest

from hypervector.commands.registry import (
    ACTIONS,
    CONVERTERS,
    GROUP_ORDER,
    LEGACY_ALIASES,
    LEGACY_GROUPS,
    RESERVED_DESTS,
    RETIRED,
    argument_dest,
    command_specs,
    fee_model_table,
    fragment,
    groups,
    iter_arguments,
    visible_flags,
)

SPEC_ROOT = files("hypervector.commands").joinpath("specs")
KINDS = {"inprocess", "operation", "passthrough"}
AUTHORITIES = {"live", "request", "simulate", "passthrough", "none"}
ENVIRONMENTS = {"live-credentials", "oxa", "models"}
AUTHORITY_FLAGS = {"--enabled", "--i-accept-live-risk"}
BANNED_SPELLINGS = {"--asset", "--coin", "--interval", "--timeout", "--lookback"}
BANNED_SPELLINGS |= {"--output", "--path"}
ARGUMENT_KEYS = {
    "flags",
    "options",
    "required",
    "legacy_flags",
    "transport",
    "data_default",
    "exclusive_group",
    "hidden",
}
# 0xArchive page sizes differ by endpoint: candles allow 10000, other feeds 1000.
CONVERTER_VARIANTS = {"--limit": {"int", "page_limit"}}
REFUSED = {
    "live check",
    "live start",
    "live request",
    "live audit-delta",
    "live validate",
    "live backup",
    "live backup-verify",
    "live rollback-profile",
    "live supervisor",
}
ALL_SPECS = [(f"{g} {a}", spec) for g, a, spec in command_specs()]


def _raw_specs() -> list[tuple[str, dict]]:
    result = []
    for directory in SPEC_ROOT.iterdir():
        if directory.name == "_fragments" or not directory.is_dir():
            continue
        for resource in directory.iterdir():
            result.append(
                (f"{directory.name}/{resource.name}", json.loads(resource.read_text()))
            )
    return result


def test_spec_directories_are_known_groups() -> None:
    names = {item.name for item in SPEC_ROOT.iterdir() if item.is_dir()}
    assert names - {"_fragments"} <= set(GROUP_ORDER)
    assert set(ACTIONS) <= set(GROUP_ORDER)


@pytest.mark.parametrize(("name", "spec"), _raw_specs())
def test_raw_spec_schema_and_help(name: str, spec: dict) -> None:
    assert spec["schema"] == 2, name
    assert "name" not in spec and "action" not in spec, name
    assert len(spec["help"]) >= 8, name
    assert spec["kind"] in KINDS, name
    assert spec["authority"] in AUTHORITIES, name
    assert spec["data_root"] in {"honored", "refused"}, name
    assert set(spec.get("environment", [])) <= ENVIRONMENTS, name
    for argument in spec.get("arguments", []):
        assert set(argument) <= ARGUMENT_KEYS, (name, argument)
        assert "required" not in argument["options"], (name, argument)


def test_fragments_are_schema_two() -> None:
    for item in SPEC_ROOT.joinpath("_fragments").iterdir():
        assert json.loads(item.read_text())["schema"] == 2, item.name


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_kind_contract(command: str, spec: dict) -> None:
    if spec["kind"] == "operation":
        assert str(spec["operation"]).startswith("hypervector.operations."), command
    elif spec["kind"] == "passthrough":
        positionals = [
            a for a in iter_arguments(spec) if not a["flags"][0].startswith("-")
        ]
        assert len(positionals) == 1 and positionals[0]["options"]["nargs"] == "..."
        assert spec["handler"]
    else:
        assert ":" in spec["handler"], command
    if spec.get("preflight"):
        assert ":" in spec["preflight"], command


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_authority_rules(command: str, spec: dict) -> None:
    flags = {flag for flag, _ in visible_flags(spec)}
    if spec["authority"] == "none":
        assert not flags & AUTHORITY_FLAGS, command
    if spec["authority"] == "live":
        assert AUTHORITY_FLAGS <= flags, command
        assert "live-credentials" in spec["environment"], command
    if "live-credentials" in spec["environment"]:
        assert spec["authority"] == "live", command


def test_refused_data_root_set() -> None:
    refused = {command for command, spec in ALL_SPECS if spec["data_root"] == "refused"}
    assert refused == REFUSED
    for command, spec in ALL_SPECS:
        if spec["data_root"] == "refused":
            assert len(spec["data_root_reason"]) >= 8, command


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_data_defaults_are_relative_and_only_on_honored_specs(
    command: str, spec: dict
) -> None:
    for argument in iter_arguments(spec):
        default = argument["options"].get("default")
        assert not (isinstance(default, str) and default.startswith("data/")), command
        if argument.get("data_default"):
            assert spec["data_root"] == "honored", command
            assert argument["options"].get("default") is None, command
            assert not str(argument["data_default"]).startswith(("/", "data/"))


VERSION_TOKENS = re.compile(r"(?i)\b(phase|tui|historical|v[0-9]+|20[0-9]{2})\b")


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_help_has_no_version_phase_or_date_tokens(command: str, spec: dict) -> None:
    texts = [spec["help"], spec.get("description", "")]
    texts += [a["options"].get("help", "") for a in iter_arguments(spec)]
    for text in texts:
        assert not VERSION_TOKENS.search(text), (command, text)


def test_banned_canonical_spellings_never_appear() -> None:
    for command, spec in ALL_SPECS:
        flags = {flag for flag, _ in visible_flags(spec)}
        assert not flags & BANNED_SPELLINGS, (command, flags & BANNED_SPELLINGS)


def test_each_visible_spelling_has_one_dest_and_converter() -> None:
    seen: dict[str, set[tuple[str, object]]] = defaultdict(set)
    for _, spec in ALL_SPECS:
        for flag, argument in visible_flags(spec):
            seen[flag].add((argument_dest(argument), argument["options"].get("type")))
    conflicts = {}
    for flag, pairs in seen.items():
        dests = {dest for dest, _ in pairs}
        converters = {converter for _, converter in pairs}
        if len(dests) > 1 or (
            len(converters) > 1 and converters != CONVERTER_VARIANTS.get(flag)
        ):
            conflicts[flag] = pairs
    assert not conflicts


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_options_are_well_formed(command: str, spec: dict) -> None:
    for argument in iter_arguments(spec):
        options = argument["options"]
        if options.get("action") == "store_true":
            assert options.get("default", False) is False, (command, argument["flags"])
        if "type" in options:
            assert options["type"] in CONVERTERS, (command, options["type"])
        assert argument_dest(argument) not in RESERVED_DESTS, (
            command,
            argument["flags"],
        )
        if not argument.get("hidden"):
            assert len(options.get("help", "")) >= 8, (command, argument["flags"])
            assert "%" not in options["help"].replace("%%", ""), command
        if "exclusive_group" in argument:
            assert argument["exclusive_group"] < len(spec["exclusive_groups"])


@pytest.mark.parametrize(("command", "spec"), ALL_SPECS)
def test_sections_follow_the_group(command: str, spec: dict) -> None:
    group = command.split()[0]
    sections = groups()["groups"][group].get("sections")
    if sections:
        assert spec.get("section") in sections, command
    else:
        assert "section" not in spec, command


def test_legacy_tables_never_shadow_canonical_names() -> None:
    canonical = {command for command, _ in ALL_SPECS}
    for key, legacy in LEGACY_ALIASES.items():
        assert key not in GROUP_ORDER and key not in canonical, key
        assert " ".join(legacy.words) in canonical, key
    assert not set(LEGACY_ALIASES) & set(RETIRED)
    assert not LEGACY_GROUPS & set(GROUP_ORDER)
    for key in RETIRED:
        assert key not in GROUP_ORDER and key not in canonical, key
    for group in LEGACY_GROUPS:
        assert group in RETIRED


def test_default_actions_exist() -> None:
    for group, meta in groups()["groups"].items():
        if "default_action" in meta:
            assert meta["default_action"] in ACTIONS[group], group


def test_fee_model_choices_match_the_cost_models() -> None:
    from hypervector.sweep.costs import COST_MODEL_ALIASES, COST_MODEL_NAMES

    names, aliases = fee_model_table()
    assert names == COST_MODEL_NAMES
    assert aliases == COST_MODEL_ALIASES
    [argument] = fragment("fees")["arguments"]
    assert tuple(argument["options"]["choices"]) == COST_MODEL_NAMES


def test_exit_mode_choices_match_the_exit_models() -> None:
    from hypervector.export.schema import VALID_TP_SL_MODES
    from hypervector.sweep.exits import EXIT_MODES

    [mode] = [
        a for a in fragment("exits")["arguments"] if a["flags"] == ["--exit-mode"]
    ]
    assert set(mode["options"]["choices"]) == set(EXIT_MODES) == VALID_TP_SL_MODES


def test_timeframe_choices_match_the_data_sources() -> None:
    from hypervector.data.hl import _INTERVAL_MS
    from hypervector.data.oxa_candle_request import _INTERVALS

    [market] = [
        a for a in fragment("market")["arguments"] if a["flags"] == ["--timeframe"]
    ]
    assert set(market["options"]["choices"]) == set(_INTERVAL_MS)
    candle = next(
        spec for command, spec in ALL_SPECS if command == "archive candle-fetch"
    )
    [timeframe] = [a for a in candle["arguments"] if a["flags"] == ["--timeframe"]]
    assert set(timeframe["options"]["choices"]) == set(_INTERVALS)
