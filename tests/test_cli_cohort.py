"""First-class CLI coverage for the shared bidirectional cohort."""

from __future__ import annotations

import pytest
from pathlib import Path

from hypervector.cli import build_parser, main
from hypervector.commands import operations
from hypervector.commands.common import CommandRefused
from hypervector.commands.operations import operation_argv

_CLI_SKILL = Path("skills/hypervector-cli/SKILL.md")
_PROFILE = ["--config", "profile.toml"]


def test_live_command_forwards_both_explicit_authority_flags() -> None:
    """Headless live execution remains double-armed at the script boundary."""
    args = build_parser().parse_args(
        [
            "live",
            "start",
            *_PROFILE,
            "--enabled",
            "--i-accept-live-risk",
            "--max-polls",
            "2",
        ]
    )

    command = operation_argv(args)

    assert command[1:3] == (
        "-m",
        "hypervector.operations.multi_asset_bidirectional_live",
    )
    assert command[-4:] == (
        "--enabled",
        "--i-accept-live-risk",
        "--max-polls",
        "2",
    )


def test_live_recovery_flag_is_forwarded_without_weakening_double_arm() -> None:
    """Explicit crash recovery reaches the backend only through live authority."""
    args = build_parser().parse_args(
        [
            "live",
            "start",
            *_PROFILE,
            "--enabled",
            "--i-accept-live-risk",
            "--resume-transition-drain",
        ]
    )

    command = operation_argv(args)

    assert command[-3:] == (
        "--enabled",
        "--i-accept-live-risk",
        "--resume-transition-drain",
    )


def test_audit_command_is_report_only_and_requires_an_output() -> None:
    """Audit CLI resolves a non-executing immutable-report command."""
    args = build_parser().parse_args(
        ["live", "audit", "--out", "audit.json", "--run-id", "run-1"]
    )

    command = operation_argv(args)

    assert command[1:3] == (
        "-m",
        "hypervector.operations.multi_asset_bidirectional_live_audit",
    )
    assert command[command.index("--run-id") + 1] == "run-1"
    assert command[command.index("--out") + 1] == "audit.json"
    assert command[command.index("--history-scope") + 1] == "current-run"
    assert "--enabled" not in command


def test_audit_delta_command_binds_two_prefixes_without_live_authority() -> None:
    """The first-class delta command must remain immutable and report-only."""
    args = build_parser().parse_args(
        [
            "live",
            "audit-delta",
            "--before",
            "before.json",
            "--after",
            "after.json",
            "--out",
            "delta.json",
        ]
    )

    command = operation_argv(args)

    assert command[1:3] == ("-m", "hypervector.operations.cohort_live_audit_delta")
    assert command[-6:] == (
        "--before",
        "before.json",
        "--after",
        "after.json",
        "--out",
        "delta.json",
    )
    assert "--enabled" not in command
    assert "--i-accept-live-risk" not in command


def test_cli_skill_documents_prefix_delta_evidence_boundaries() -> None:
    """Operator guidance must separate resolved, provisional, and technical deltas."""
    text = _CLI_SKILL.read_text(encoding="utf-8")

    assert "live audit-delta" in text
    assert "resolved execution" in text
    assert "provisional open-lifecycle" in text
    assert "known technical-gap growth" in text
    assert "execution_authority=none" in text


def test_research_import_command_has_no_execution_authority() -> None:
    """Cohort journal ingestion resolves only the report-only database script."""
    args = build_parser().parse_args(
        ["db", "import-cohort", "--database", "research.duckdb"]
    )

    command = operation_argv(args)

    assert command[1:3] == (
        "-m",
        "hypervector.operations.multi_asset_bidirectional_research_import",
    )
    assert command[-2:] == ("--database", "research.duckdb")
    assert "--enabled" not in command


@pytest.mark.parametrize(
    "flags",
    ([], ["--enabled"], ["--i-accept-live-risk"]),
)
def test_live_boundaries_require_both_explicit_authority_flags(
    flags: list[str],
) -> None:
    """No cohort CLI path may weaken the existing double-arm boundary."""
    args = build_parser().parse_args(["live", "start", *_PROFILE, *flags])

    with pytest.raises(CommandRefused, match="both --enabled and --i-accept-live-risk"):
        operations.run_operation(args)


def test_main_reports_live_refusal_without_a_traceback(capsys) -> None:
    """Operator mistakes fail closed with one actionable CLI message."""
    assert main(["live", "start", *_PROFILE]) == 2

    captured = capsys.readouterr()
    assert "both --enabled and --i-accept-live-risk" in captured.err
    assert "Traceback" not in captured.err


def test_live_start_requires_an_explicit_profile() -> None:
    """The live backend never falls back to a module default profile."""
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["live", "start", "--enabled", "--i-accept-live-risk"]
        )
    assert exc.value.code == 2
