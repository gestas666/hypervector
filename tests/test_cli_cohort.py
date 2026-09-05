"""First-class CLI coverage for the shared bidirectional cohort."""

from __future__ import annotations

import pytest
from pathlib import Path

from hypervector.cli import build_parser, main
from hypervector.cli_cohort import cohort_command

_CLI_SKILL = Path("skills/hypervector-cli/SKILL.md")


def test_monitor_command_is_read_only_and_uses_current_launcher() -> None:
    """Monitor mode attaches without forwarding live authority flags."""
    args = build_parser().parse_args(["cohort-tui", "--mode", "monitor"])

    command = cohort_command(args)

    assert command[1].endswith("scripts/multi_asset_bidirectional_canary_tui.py")
    assert command[-2:] == ("--mode", "monitor")
    assert "--enabled" not in command
    assert "--i-accept-live-risk" not in command


def test_monitor_command_forwards_accounting_epoch_bundle() -> None:
    """The first-class monitor preserves the checkpoint accounting lineage."""
    bundle = "data/backups/bidirectional_cohort/accounting_epochs/v61"
    args = build_parser().parse_args(
        [
            "cohort-tui",
            "--mode",
            "monitor",
            "--accounting-epoch-bundle",
            bundle,
        ]
    )

    command = cohort_command(args)

    index = command.index("--accounting-epoch-bundle")
    assert command[index + 1] == bundle
    assert "--enabled" not in command
    assert "--i-accept-live-risk" not in command


def test_live_command_forwards_both_explicit_authority_flags() -> None:
    """Headless live execution remains double-armed at the script boundary."""
    args = build_parser().parse_args(
        ["cohort-live", "--enabled", "--i-accept-live-risk", "--max-polls", "2"]
    )

    command = cohort_command(args)

    assert command[1].endswith("scripts/multi_asset_bidirectional_live.py")
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
            "cohort-live",
            "--enabled",
            "--i-accept-live-risk",
            "--resume-transition-drain",
        ]
    )

    command = cohort_command(args)

    assert command[-3:] == (
        "--enabled",
        "--i-accept-live-risk",
        "--resume-transition-drain",
    )


def test_tui_live_recovery_flag_reaches_the_unified_supervisor() -> None:
    """The one-terminal path can recover an interrupted active drain explicitly."""
    args = build_parser().parse_args(
        [
            "cohort-tui",
            "--mode",
            "live",
            "--enabled",
            "--i-accept-live-risk",
            "--resume-transition-drain",
        ]
    )

    command = cohort_command(args)

    assert command[-5:] == (
        "--mode",
        "live",
        "--enabled",
        "--i-accept-live-risk",
        "--resume-transition-drain",
    )
    assert "--resume-transition-drain" in command


def test_tui_live_forwards_the_exact_explicit_candidate_config() -> None:
    """The first-class CLI preserves an operator-selected profile path."""
    candidate = (
        "configs/"
        "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml"
    )
    args = build_parser().parse_args(
        [
            "cohort-tui",
            "--mode",
            "live",
            "--config",
            candidate,
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    command = cohort_command(args)

    config_index = command.index("--config")
    assert command[config_index + 1] == candidate
    assert command[-4:] == (
        "--mode",
        "live",
        "--enabled",
        "--i-accept-live-risk",
    )


def test_audit_command_is_report_only_and_requires_an_output() -> None:
    """Audit CLI resolves a non-executing immutable-report command."""
    args = build_parser().parse_args(
        ["cohort-live-audit", "--out", "audit.json", "--run-id", "run-1"]
    )

    command = cohort_command(args)

    assert command[1].endswith("scripts/multi_asset_bidirectional_live_audit.py")
    assert command[-4:] == ("--run-id", "run-1", "--out", "audit.json")
    assert "--enabled" not in command


def test_audit_delta_command_binds_two_prefixes_without_live_authority() -> None:
    """The first-class delta command must remain immutable and report-only."""
    args = build_parser().parse_args(
        [
            "cohort-live-audit-delta",
            "--before",
            "before.json",
            "--after",
            "after.json",
            "--out",
            "delta.json",
        ]
    )

    command = cohort_command(args)

    assert command[1].endswith("scripts/cohort_live_audit_delta.py")
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

    assert "cohort-live-audit-delta" in text
    assert "resolved execution" in text
    assert "provisional open-lifecycle" in text
    assert "known technical-gap growth" in text
    assert "execution_authority=none" in text


def test_research_import_command_has_no_execution_authority() -> None:
    """Cohort journal ingestion resolves only the report-only database script."""
    args = build_parser().parse_args(
        ["cohort-research-import", "--database", "research.duckdb"]
    )

    command = cohort_command(args)

    assert command[1].endswith("scripts/multi_asset_bidirectional_research_import.py")
    assert command[-2:] == ("--database", "research.duckdb")
    assert "--enabled" not in command


@pytest.mark.parametrize(
    "argv",
    (
        ["cohort-live"],
        ["cohort-live", "--enabled"],
        ["cohort-tui", "--mode", "live"],
    ),
)
def test_live_boundaries_require_both_explicit_authority_flags(
    argv: list[str],
) -> None:
    """No cohort CLI path may weaken the existing double-arm boundary."""
    args = build_parser().parse_args(argv)

    with pytest.raises(ValueError, match="both --enabled and --i-accept-live-risk"):
        cohort_command(args)


def test_main_reports_live_refusal_without_a_traceback(capsys) -> None:
    """Operator mistakes fail closed with one actionable CLI message."""
    assert main(["cohort-live"]) == 2

    captured = capsys.readouterr()
    assert "both --enabled and --i-accept-live-risk" in captured.err
    assert "Traceback" not in captured.err
