"""Candidate preview commands must keep every authority and ledger disarmed."""

from pathlib import Path

from hypervector.live.cohort_candidate_preview import build_candidate_preview

CONFIG = Path("configs/multi_asset_growth_first_5000_noncrypto_research_v89.toml")


def test_preview_binds_seven_assets_to_isolated_observer(tmp_path: Path) -> None:
    """The candidate must retain seven routes without targeting live ledgers."""
    launch = build_candidate_preview(
        CONFIG, tmp_path, Path("../backtest-lab/backtest_lab")
    )
    assert launch.config.mode == "observe"
    assert len(launch.config.symbols) == 7
    assert launch.config.cohort_ledger == tmp_path / "decisions.jsonl"
    assert launch.config.stop_file == tmp_path / "STOP"
    assert launch.backend_command is not None
    assert "scripts/multi_asset_bidirectional_observe.py" in launch.backend_command
    assert launch.backend_command[-2:] == ("--ledger-root", str(tmp_path))
    assert launch.dependency_command is None
    assert launch.accounting_epoch is None


def test_preview_checkpoint_tui_and_audit_share_isolated_identity(
    tmp_path: Path,
) -> None:
    """Neither the display nor its checkpoint may read the old V88 projection."""
    launch = build_candidate_preview(
        CONFIG, tmp_path, Path("../backtest-lab/backtest_lab")
    )
    commands = (
        launch.backend_command,
        launch.checkpoint_command,
        launch.tui_command,
        launch.audit_command,
    )
    for command in commands:
        assert command is not None
        assert "--enabled" not in command
        assert "--i-accept-live-risk" not in command
        assert not any("data/live/" in item for item in command)
    checkpoint = launch.checkpoint_command
    assert checkpoint is not None
    assert checkpoint[checkpoint.index("--out") + 1] == str(
        tmp_path / "checkpoint.json"
    )
    tui = launch.tui_command
    assert tui[tui.index("--cohort-checkpoint") + 1] == str(
        tmp_path / "checkpoint.json"
    )
    assert tui[tui.index("--backend-ledger") + 1] == str(tmp_path / "decisions.jsonl")
    assert tui[tui.index("--cohort-command-inbox") + 1] == str(
        tmp_path / "operator_commands"
    )
    audit = launch.audit_command
    assert audit is not None
    assert audit[audit.index("--out-dir") + 1] == str(tmp_path / "audits")
