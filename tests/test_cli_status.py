"""Status inventory (schema 3) and command discoverability."""

from __future__ import annotations

import argparse
import json

from hypervector.cli import CLI_COMMANDS, LEGACY_ALIASES, RETIRED, build_parser, main


def _status(tmp_path, capsys, monkeypatch) -> dict:
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(tmp_path / "data"), "system", "status"])
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def test_cli_status_inventory(tmp_path, capsys, monkeypatch):
    rep = _status(tmp_path, capsys, monkeypatch)
    assert rep["ok"] is True
    assert rep["schema_version"] == 3
    assert rep["pipeline"]["paper_shadow_dry_run"] is True
    assert rep["pipeline"]["tui_gui"] is False
    assert rep["paper"]["no_submit"] is True
    assert "paper run" in rep["paper"]["commands"]
    assert rep["commands"] == list(CLI_COMMANDS)
    assert all(" " in command for command in rep["commands"])
    assert "sekrit" not in json.dumps(rep)
    assert not (tmp_path / "data").exists()


def test_cli_status_live_block_comes_from_the_cohort_backend(
    tmp_path, capsys, monkeypatch
):
    live = _status(tmp_path, capsys, monkeypatch)["live"]
    assert live["backend"] == "hypervector.operations.multi_asset_bidirectional_live"
    assert live["start_command"] == "live start"
    assert live["check_command"] == "live check"
    assert {"live start", "live check", "live checkpoint"} <= set(live["commands"])
    assert live["requires_for_start"] == [
        "--config",
        "--enabled",
        "--i-accept-live-risk",
    ]
    assert live["enabled_default"] is False
    assert live["armed"] is False


def test_cli_status_lists_legacy_aliases_and_retired_names(
    tmp_path, capsys, monkeypatch
):
    rep = _status(tmp_path, capsys, monkeypatch)
    assert rep["legacy_aliases"]["cohort-live"] == "live start"
    assert rep["legacy_aliases"]["sweep-up"] == "backtest sweep --track uptrend"
    assert rep["legacy_aliases"]["status"] == "system status"
    assert set(rep["legacy_aliases"]) == set(LEGACY_ALIASES)
    assert rep["retired"] == RETIRED
    assert "research db-journal-append" in rep["retired"]


def test_cli_status_reports_oxa_key_presence_only(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OXA_API_KEY", "configured-oxa-secret")
    rep = _status(tmp_path, capsys, monkeypatch)
    oxa = rep["capabilities"]["0xarchive"]
    assert oxa["api_key_configured"] is True
    assert oxa["credential_env"] == "OXA_API_KEY"
    assert "configured-oxa-secret" not in json.dumps(rep)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )


def test_all_cli_commands_registered():
    parser = build_parser()
    registered = {
        f"{group} {action}"
        for group, group_parser in _subparsers(parser).items()
        for action in _subparsers(group_parser)
    }
    assert registered == set(CLI_COMMANDS)
    root_help = parser.format_help()
    assert "cohort-tui" not in root_help
    assert {
        "live start",
        "live audit",
        "db import-cohort",
        "paper run",
    } <= set(CLI_COMMANDS)
    assert not {
        "paper shadow",
        "paper shadow-reset",
        "paper compare",
        "regime align",
        "tune regime",
    } & set(CLI_COMMANDS)


def test_root_description_names_pipeline():
    desc = build_parser().description or ""
    assert "research" in desc.lower() or "phase2" in desc.lower()
    assert "paper" in desc.lower() or "shadow" in desc.lower()
    assert "live" in desc.lower()
