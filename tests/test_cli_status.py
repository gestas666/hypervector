"""Phase 4c: status inventory + command discoverability."""

from __future__ import annotations

import json

from hypervector.cli import CLI_COMMANDS, build_parser, main


def test_cli_status_inventory(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(tmp_path / "data"), "status"])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is True
    assert rep["pipeline"]["paper_shadow_dry_run"] is True
    assert rep["pipeline"]["live_submit"] is True
    assert rep["pipeline"]["tui_gui"] is False
    assert rep["paper"]["no_submit"] is True
    assert rep["live"]["submit_wired"] is True
    assert rep["live"]["can_start"] is False
    assert "live-run" in rep["live"]["commands"]
    assert "paper-run" in rep["paper"]["commands"]
    assert set(CLI_COMMANDS).issubset(set(rep["commands"]))
    assert "sekrit" not in json.dumps(rep)


def test_all_cli_commands_registered():
    parser = build_parser()
    # subparsers stored on first action of type that has choices
    choices = None
    for action in parser._actions:
        if getattr(action, "choices", None) and isinstance(action.choices, dict):
            choices = set(action.choices.keys())
            break
    assert choices is not None
    missing = set(CLI_COMMANDS) - choices
    assert not missing, f"CLI_COMMANDS missing from parser: {missing}"
    # Every inventory command must be in the live parser (no orphans the other way optional)
    assert "status" in choices
    assert "live-report" in choices
    assert "hypervelocity-tui" in choices
    assert "hypervelocity-shadow-reset" in choices
    assert "cohort-tui" in choices
    assert "cohort-live" in choices
    assert "cohort-live-audit" in choices
    assert "cohort-research-import" in choices


def test_root_description_names_pipeline():
    desc = build_parser().description or ""
    assert "research" in desc.lower() or "phase2" in desc.lower()
    assert "paper" in desc.lower() or "shadow" in desc.lower()
    assert "live" in desc.lower()
