"""Unified launcher command tests for the multi-asset cohort TUI."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_bidirectional_canary_tui.py"
)
V14 = "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
V25 = "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
V34 = "configs/multi_asset_bidirectional_route_hardening_canary_v34.toml"
V35 = "configs/multi_asset_bidirectional_all_live_canary_v35.toml"
V36 = "configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml"
V37 = "configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml"
V39 = (
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
GROWTH_PREFLIGHT = "data/runtime/bidirectional_cohort/latest_growth_5000_preflight.json"
V39_PREFLIGHT = (
    "data/runtime/bidirectional_cohort/latest_current_500_v39_preflight.json"
)
V63 = (
    "configs/"
    "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63.toml"
)
V64 = (
    "configs/multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64.toml"
)
V64_PREFLIGHT = (
    "data/logs/research/bidirectional_cohort/"
    "v64_gold_removed_flat_preflight_20260901T0456Z.json"
)
V67 = (
    "configs/"
    "multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67.toml"
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_canary_tui", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_observe_default_starts_disarmed_backend_and_tui() -> None:
    """The default launcher produces current data without execution authority."""
    module = _load_module()

    launch = module.resolve_launch(
        module.build_parser().parse_args([]),
        credentials_present=False,
    )
    assert launch.backend_command is not None
    assert launch.config.source_path == Path(V36)
    assert len(launch.config.symbols) == 9
    assert "scripts/multi_asset_bidirectional_observe.py" in launch.backend_command
    assert "--enabled" not in launch.backend_command
    assert "--i-accept-live-risk" not in launch.backend_command
    assert launch.checkpoint_command is not None
    assert "scripts/multi_asset_bidirectional_observer_checkpoint.py" in (
        launch.checkpoint_command
    )
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command
    assert launch.audit_command is not None
    assert "scripts/multi_asset_bidirectional_observer_audit.py" in (
        launch.audit_command
    )
    assert launch.audit_command[-2:] == (
        "--out-dir",
        "data/logs/research/bidirectional_cohort",
    )
    assert "--backend-ledger" in launch.tui_command
    assert "--release" in launch.tui_command
    assert "--cohort-checkpoint" in launch.tui_command
    assert "--hype-l2-observer-status" in launch.tui_command
    assert "--hip3-roster-status" in launch.tui_command
    assert "data/runtime/research/hip3_roster_latest.json" in launch.tui_command
    assert "data/live/bidirectional_cohort/decisions.jsonl" in launch.tui_command
    initial = launch.tui_command.index("--initial-tab")
    assert launch.tui_command[initial + 1] == "2"


def test_explicit_monitor_attaches_with_report_only_checkpoint_recovery() -> None:
    """Attach mode can recover stale telemetry without starting a backend."""
    module = _load_module()

    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", V14]),
        credentials_present=False,
    )

    assert launch.backend_command is None
    assert launch.checkpoint_command is not None
    assert "scripts/multi_asset_bidirectional_live_checkpoint.py" in (
        launch.checkpoint_command
    )
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command
    assert launch.audit_command is None
    assert "--detached-lifecycle" in launch.tui_command
    assert "--cohort-checkpoint" in launch.tui_command
    assert "--hype-l2-observer-status" in launch.tui_command


def test_v67_omits_retired_incompatible_hype_l2_observer() -> None:
    """V67 must not render a stale observer for a retired entry mechanism."""
    module = _load_module()

    launch = module.resolve_launch(
        module.build_parser().parse_args(
            [
                "--mode",
                "live",
                "--config",
                V67,
                "--enabled",
                "--i-accept-live-risk",
            ]
        ),
        credentials_present=True,
    )

    assert "--hype-l2-observer-status" not in launch.tui_command
    assert "data/runtime/research/hype_l2_ridge_observer_latest.json" not in (
        launch.tui_command
    )


def test_monitor_separates_active_v35_from_staged_v36_identity() -> None:
    """Monitor binds the ledger to v35 while comparing v36 report-only."""
    module = _load_module()

    launch = module.resolve_launch(
        module.build_parser().parse_args(
            [
                "--mode",
                "monitor",
                "--config",
                V35,
                "--staged-config",
                V36,
            ]
        ),
        credentials_present=False,
    )

    assert launch.backend_command is None
    assert launch.config.profile_id == "multi_asset_bidirectional_all_live_canary_v35"
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id == (
        "multi_asset_bidirectional_evidence_roster_canary_v36"
    )
    assert launch.config.cohort_ledger == launch.staged_config.cohort_ledger
    assert launch.checkpoint_command is not None
    checkpoint_config = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint_config + 1] == V36
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command


def test_current_v35_v39_command_is_attach_only_and_read_only() -> None:
    """The documented transition command cannot launch or arm a backend."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            V35,
            "--staged-config",
            V39,
            "--growth-preflight",
            V39_PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.staged_config is not None
    assert launch.staged_config.profile_id.endswith("current_canary_v39")
    assert "--detached-lifecycle" in launch.tui_command
    assert "--enabled" not in launch.tui_command
    assert "--i-accept-live-risk" not in launch.tui_command
    checkpoint_config = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint_config + 1] == V39
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command


def test_monitor_rejects_a_staged_profile_for_another_ledger(
    tmp_path: Path,
) -> None:
    """A next profile cannot be compared against an unrelated runtime ledger."""
    module = _load_module()
    staged = tmp_path / "foreign.toml"
    staged.write_text(
        Path(V36)
        .read_text(encoding="utf-8")
        .replace(
            'cohort_ledger = "data/live/bidirectional_cohort/decisions.jsonl"',
            'cohort_ledger = "data/live/foreign/decisions.jsonl"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="same cohort ledger"):
        module.resolve_launch(
            module.build_parser().parse_args(
                [
                    "--mode",
                    "monitor",
                    "--config",
                    V35,
                    "--staged-config",
                    str(staged),
                ]
            ),
            credentials_present=False,
        )


def test_staged_profile_comparison_is_monitor_only() -> None:
    """Observe/live launch paths cannot mix a second profile identity."""
    module = _load_module()

    with pytest.raises(Exception, match="requires monitor mode"):
        module.resolve_launch(
            module.build_parser().parse_args(["--staged-config", V36]),
            credentials_present=False,
        )


def test_growth_preflight_is_bound_to_a_staged_monitor_profile() -> None:
    """Sizing evidence reaches only a read-only staged monitor command."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            V35,
            "--staged-config",
            V37,
            "--growth-preflight",
            GROWTH_PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    option = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[option + 1] == GROWTH_PREFLIGHT
    assert launch.backend_command is None


def test_v64_monitor_command_is_staged_report_only_and_gold_free() -> None:
    """The exact V64 TUI command compares against V63 without starting execution."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "monitor",
            "--config",
            V63,
            "--staged-config",
            V64,
            "--growth-preflight",
            V64_PREFLIGHT,
        ]
    )

    launch = module.resolve_launch(args, credentials_present=False)

    assert launch.backend_command is None
    assert launch.audit_command is None
    assert launch.staged_config is not None
    assert "xyz:GOLD" in launch.config.symbols
    assert "xyz:GOLD" not in launch.staged_config.symbols
    assert len(launch.staged_config.executable_provider_directions) == 23
    checkpoint_config = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint_config + 1] == V64
    preflight = launch.tui_command.index("--growth-preflight")
    assert launch.tui_command[preflight + 1] == V64_PREFLIGHT
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command


def test_growth_preflight_without_staged_monitor_is_rejected() -> None:
    """A candidate sizing artifact cannot be mislabeled as current runtime state."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--mode", "monitor", "--config", V35, "--growth-preflight", GROWTH_PREFLIGHT]
    )

    with pytest.raises(Exception, match="requires --staged-config"):
        module.resolve_launch(args, credentials_present=False)


def test_monitor_recovers_a_stale_checkpoint_while_tui_is_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale monitor attach owns one report-only checkpoint child."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", V14]),
        credentials_present=False,
    )
    checkpoint = SimpleNamespace(label="checkpoint", poll=lambda: None)
    calls: list[object] = []
    freshness = iter((False, True))
    monkeypatch.setattr(module, "_CHECKPOINT_LOG", tmp_path / "checkpoint.log")
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda _config: next(freshness))
    monkeypatch.setattr(
        module,
        "cohort_checkpoint_writer_active",
        lambda _output: False,
    )
    monkeypatch.setattr(
        module,
        "active_ledger_identity",
        lambda _config: SimpleNamespace(run_id="active-run"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda command, **_kwargs: calls.append(command) or checkpoint,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, *, check: calls.append(command)
        or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        module,
        "_stop_checkpoint_monitor",
        lambda process: calls.append(("stop", process.label)),
    )

    assert module.run_supervisor(launch) == 0
    bound_checkpoint = (*launch.checkpoint_command, "--run-id", "active-run")
    assert calls == [
        bound_checkpoint,
        launch.tui_command,
        ("stop", "checkpoint"),
    ]


def test_monitor_reuses_a_fresh_external_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy producer is reused instead of duplicated."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", V14]),
        credentials_present=False,
    )
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda _config: True)
    monkeypatch.setattr(
        module,
        "cohort_checkpoint_writer_active",
        lambda _output: True,
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("checkpoint must not be duplicated"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, *, check: SimpleNamespace(returncode=0),
    )

    assert module.run_supervisor(launch) == 0


def test_monitor_starts_writer_when_fresh_checkpoint_is_orphaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recent artifact without a writer cannot age out during the session."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", V14]),
        credentials_present=False,
    )
    checkpoint = SimpleNamespace(label="checkpoint")
    calls: list[object] = []
    monkeypatch.setattr(module, "_CHECKPOINT_LOG", tmp_path / "checkpoint.log")
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda _config: True)
    monkeypatch.setattr(
        module,
        "cohort_checkpoint_writer_active",
        lambda _output: False,
    )
    monkeypatch.setattr(
        module,
        "active_ledger_identity",
        lambda _config: SimpleNamespace(run_id="active-run"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda command, **_kwargs: calls.append(command) or checkpoint,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, *, check: calls.append(command)
        or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        module,
        "_stop_checkpoint_monitor",
        lambda process: calls.append(("stop", process.label)),
    )

    assert module.run_supervisor(launch) == 0
    bound_checkpoint = (*launch.checkpoint_command, "--run-id", "active-run")
    assert calls == [
        bound_checkpoint,
        launch.tui_command,
        ("stop", "checkpoint"),
    ]


def test_monitor_reuses_an_active_writer_while_checkpoint_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow refresh cannot cause the monitor to start a competing writer."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(["--mode", "monitor", "--config", V14]),
        credentials_present=False,
    )
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda _config: False)
    monkeypatch.setattr(
        module,
        "cohort_checkpoint_writer_active",
        lambda _output: True,
        raising=False,
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("active writer must be reused"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, *, check: SimpleNamespace(returncode=0),
    )

    assert module.run_supervisor(launch) == 0


def test_staged_monitor_refuses_an_unverified_active_checkpoint_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A foreign writer cannot silently replace the selected next identity."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(
            [
                "--mode",
                "monitor",
                "--config",
                V35,
                "--staged-config",
                V36,
            ]
        ),
        credentials_present=False,
    )
    monkeypatch.setattr(module, "_checkpoint_is_fresh", lambda *_configs: False)
    monkeypatch.setattr(
        module,
        "cohort_checkpoint_writer_active",
        lambda _output: True,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "TUI must not attach to an unknown writer"
        ),
    )

    with pytest.raises(Exception, match="active checkpoint writer"):
        module.run_supervisor(launch)


def test_monitor_requires_an_explicit_profile_identity() -> None:
    """A monitor cannot recover telemetry through the unrelated default profile."""
    module = _load_module()

    with pytest.raises(Exception, match="monitor requires --config"):
        module.resolve_launch(
            module.build_parser().parse_args(["--mode", "monitor"]),
            credentials_present=False,
        )


def test_recent_wrong_profile_checkpoint_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recent foreign checkpoint cannot be reused or overwritten concurrently."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    config = SimpleNamespace(
        cohort_ledger=ledger,
        profile_id="profile-a",
        profile_fingerprint="fingerprint-a",
    )
    ledger.write_text(
        '{"event_type":"configuration_identity","execution_mode":"live",'
        '"live_armed":true,"run_id":"current-run","profile_id":"profile-a",'
        '"profile_fingerprint":"fingerprint-a"}\n',
        encoding="utf-8",
    )
    checkpoint = tmp_path / "latest.json"
    checkpoint.write_text(
        '{"schema_version":1,'
        '"mode":"multi_asset_bidirectional_live_checkpoint",'
        '"audit":{"run":{"run_id":"foreign","profile_id":"wrong",'
        '"profile_fingerprint":"wrong"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_CHECKPOINT_OUTPUT", checkpoint)

    with pytest.raises(Exception, match="profile identity does not match"):
        module._checkpoint_is_fresh(config)


def test_recent_prior_run_checkpoint_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recent same-profile checkpoint from a prior run cannot be reused."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    checkpoint = tmp_path / "latest.json"
    config = SimpleNamespace(
        cohort_ledger=ledger,
        profile_id="profile-a",
        profile_fingerprint="fingerprint-a",
    )
    ledger.write_text(
        '{"event_type":"configuration_identity","execution_mode":"live",'
        '"live_armed":true,"run_id":"current-run","profile_id":"profile-a",'
        '"profile_fingerprint":"fingerprint-a"}\n',
        encoding="utf-8",
    )
    checkpoint.write_text(
        '{"schema_version":1,'
        '"mode":"multi_asset_bidirectional_live_checkpoint",'
        '"audit":{"run":{"run_id":"prior-run","profile_id":"profile-a",'
        '"profile_fingerprint":"fingerprint-a"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_CHECKPOINT_OUTPUT", checkpoint)

    with pytest.raises(Exception, match="run identity does not match"):
        module._checkpoint_is_fresh(config)


def test_recent_checkpoint_requires_the_selected_staged_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current active checkpoint cannot masquerade as another next profile."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    checkpoint = tmp_path / "latest.json"
    active = SimpleNamespace(
        cohort_ledger=ledger,
        profile_id="active-profile",
        profile_fingerprint="active-fingerprint",
    )
    staged = SimpleNamespace(
        source_path=Path("configs/staged.toml"),
        profile_fingerprint="staged-fingerprint",
    )
    ledger.write_text(
        '{"event_type":"configuration_identity","execution_mode":"live",'
        '"live_armed":true,"run_id":"active-run","profile_id":"active-profile",'
        '"profile_fingerprint":"active-fingerprint"}\n',
        encoding="utf-8",
    )
    checkpoint.write_text(
        '{"schema_version":1,'
        '"mode":"multi_asset_bidirectional_live_checkpoint",'
        '"configuration_generation":{'
        '"state":"stale_runtime_configuration","matches_runtime":false,'
        '"runtime_profile_fingerprint":"active-fingerprint",'
        '"current_profile_fingerprint":"staged-fingerprint",'
        '"source_path":"configs/staged.toml",'
        '"execution_authority":"none","automatic_restart":false},'
        '"audit":{"run":{"run_id":"active-run","profile_id":"active-profile",'
        '"profile_fingerprint":"active-fingerprint"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_CHECKPOINT_OUTPUT", checkpoint)

    assert module._checkpoint_is_fresh(active, staged)
    checkpoint.write_text(
        checkpoint.read_text(encoding="utf-8").replace(
            '"current_profile_fingerprint":"staged-fingerprint"',
            '"current_profile_fingerprint":"wrong-staged-fingerprint"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="staged configuration identity"):
        module._checkpoint_is_fresh(active, staged)


def test_checkpoint_recovery_requires_the_active_ledger_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing telemetry cannot launch recovery for a foreign selected profile."""
    module = _load_module()
    ledger = tmp_path / "decisions.jsonl"
    config = SimpleNamespace(
        cohort_ledger=ledger,
        profile_id="selected-profile",
        profile_fingerprint="selected-fingerprint",
    )
    ledger.write_text(
        '{"event_type":"configuration_identity","execution_mode":"live",'
        '"live_armed":true,"run_id":"active-run","profile_id":"active-profile",'
        '"profile_fingerprint":"active-fingerprint"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_CHECKPOINT_OUTPUT", tmp_path / "missing.json")

    with pytest.raises(Exception, match="active ledger profile does not match"):
        module._checkpoint_is_fresh(config)


def test_normal_observer_tui_exit_stops_backend_then_publishes_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every supervised forward-observer session leaves immutable evidence."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args([]),
        credentials_present=False,
    )
    launch = replace(
        launch,
        config=replace(launch.config, stop_file=tmp_path / "STOP"),
    )
    calls: list[tuple[str, ...]] = []
    backend = SimpleNamespace(label="backend")
    checkpoint = SimpleNamespace(label="checkpoint")
    monkeypatch.setattr(module, "_BACKEND_LOG", tmp_path / "backend.log")
    monkeypatch.setattr(module, "capture_ledger_start", lambda _path: object())

    processes = iter((backend, checkpoint))

    def fake_popen(*_args: object, **_kwargs: object) -> SimpleNamespace:
        process = next(processes)
        calls.append(("start", process.label))
        return process

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        module,
        "_wait_for_backend",
        lambda *_args: calls.append(("ready",)),
    )
    monkeypatch.setattr(
        module, "_stop_owned_backend", lambda *_args: calls.append(("backend_stop",))
    )
    monkeypatch.setattr(
        module,
        "_stop_checkpoint_monitor",
        lambda process: calls.append(("checkpoint_stop", process.label)),
    )

    def fake_run(command: tuple[str, ...], *, check: bool) -> SimpleNamespace:
        assert check is False
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.run_supervisor(launch) == 0
    assert calls == [
        ("start", "backend"),
        ("ready",),
        ("start", "checkpoint"),
        launch.tui_command,
        ("checkpoint_stop", "checkpoint"),
        ("backend_stop",),
        (*launch.checkpoint_command, "--once"),
        launch.audit_command,
    ]


def test_explicit_live_mode_builds_one_backend_and_one_tui_command() -> None:
    """The unified live mode forwards both independent authority flags."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            V25,
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)
    assert launch.backend_command is not None
    assert "scripts/multi_asset_bidirectional_live.py" in launch.backend_command
    assert "--enabled" in launch.backend_command
    assert "--i-accept-live-risk" in launch.backend_command
    assert "--detached-lifecycle" not in launch.tui_command
    assert launch.tui_command[-1] == "data/live/bidirectional_cohort/decisions.jsonl"
    initial = launch.tui_command.index("--initial-tab")
    assert launch.tui_command[initial + 1] == "1"
    assert launch.audit_command is not None
    assert "scripts/multi_asset_bidirectional_live_audit.py" in launch.audit_command
    assert "data/live/bidirectional_cohort" in launch.audit_command
    assert launch.audit_command[-2:] == (
        "--out-dir",
        "data/logs/research/bidirectional_cohort",
    )
    assert launch.checkpoint_command is not None
    assert "scripts/multi_asset_bidirectional_live_checkpoint.py" in (
        launch.checkpoint_command
    )
    assert "--enabled" not in launch.checkpoint_command
    assert "--i-accept-live-risk" not in launch.checkpoint_command
    assert "--research-database" in launch.checkpoint_command
    assert "--venue-portfolio" in launch.checkpoint_command
    database = launch.checkpoint_command.index("--research-database")
    assert launch.checkpoint_command[database + 1] == "data/research/market.duckdb"
    cadence = launch.checkpoint_command.index("--research-sync-interval-seconds")
    assert launch.checkpoint_command[cadence + 1] == "120"
    assert "--cohort-checkpoint" in launch.tui_command
    assert "data/runtime/bidirectional_cohort/latest_checkpoint.json" in (
        launch.tui_command
    )
    assert launch.startup_timeout_seconds >= 900.0


def test_v25_checkpoint_retains_profile_bound_research_attachments() -> None:
    """A normal v25 attach must not drop its prospective research frontier."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            V25,
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.checkpoint_command is not None
    command = launch.checkpoint_command
    matrix = command.index("--opportunity-matrix")
    assert command[matrix + 1] == (
        "data/logs/research/bidirectional_cohort/"
        "v25_execution_opportunity_matrix_exlargest_20260808T2216Z.json"
    )
    supplements = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--supplemental-opportunity-matrix"
    ]
    assert supplements == [
        "data/runtime/bidirectional_cohort/latest_spcx_swing_pivot_challenger.json",
        "data/runtime/bidirectional_cohort/"
        "latest_sol_breakout_continuation_challenger.json",
        "data/runtime/bidirectional_cohort/latest_sndk_swing_pivot_challenger.json",
    ]
    journal = command.index("--asymmetric-forward-journal")
    assert command[journal + 1] == (
        "docs/research-journal/cohort-asymmetric-shared-portfolio-v1.json"
    )


def test_non_v25_checkpoint_refuses_v25_research_inheritance() -> None:
    """A different profile must not be labeled with v25 prospective evidence."""
    module = _load_module()
    candidate = Path(
        "configs/"
        "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml"
    )
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            str(candidate),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.checkpoint_command is not None
    assert "--disable-asymmetric-forward-observer" in launch.checkpoint_command
    assert "--opportunity-matrix" not in launch.checkpoint_command
    assert "--supplemental-opportunity-matrix" not in launch.checkpoint_command


def test_route_hardening_checkpoint_excludes_incompatible_eth_forward_observer() -> (
    None
):
    """A profile-bound ETH observer cannot suppress the current checkpoint."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            V34,
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.checkpoint_command is not None
    assert "--eligible-policy-forward" not in launch.checkpoint_command


def test_explicit_candidate_identity_reaches_backend_and_checkpoint() -> None:
    """A selected profile is not replaced by the stale TUI staging sidecar."""
    module = _load_module()
    candidate = Path(
        "configs/"
        "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml"
    )
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            str(candidate),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.config.source_path == candidate
    assert launch.config.profile_fingerprint == (
        "a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08"
    )
    assert launch.backend_command is not None
    backend_config = launch.backend_command.index("--config")
    assert launch.backend_command[backend_config + 1] == str(candidate)
    assert launch.checkpoint_command is not None
    checkpoint_config = launch.checkpoint_command.index("--config")
    assert launch.checkpoint_command[checkpoint_config + 1] == str(candidate)
    assert "--eligible-policy-forward" not in launch.checkpoint_command


def test_eth_transfer_profile_keeps_exact_forward_journal_after_restart() -> None:
    """The unified sidecar retains the report-only ETH lifecycle projection."""
    module = _load_module()
    config = Path(
        "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
    )
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--config",
            str(config),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.checkpoint_command is not None
    assert "--eligible-policy-forward" in launch.checkpoint_command


def test_explicit_live_drain_recovery_is_forwarded_only_to_backend() -> None:
    """The TUI remains read-only while the Python backend resumes drain state."""
    module = _load_module()
    args = module.build_parser().parse_args(
        [
            "--mode",
            "live",
            "--enabled",
            "--i-accept-live-risk",
            "--resume-transition-drain",
        ]
    )

    launch = module.resolve_launch(args, credentials_present=True)

    assert launch.backend_command is not None
    assert "--resume-transition-drain" in launch.backend_command
    assert "--resume-transition-drain" not in launch.tui_command
    assert launch.checkpoint_command is not None
    assert "--resume-transition-drain" not in launch.checkpoint_command


def test_normal_live_tui_exit_stops_backend_then_publishes_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal supervised live exit must preserve a post-stop audit artifact."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--mode", "live", "--enabled", "--i-accept-live-risk"]
    )
    launch = module.resolve_launch(args, credentials_present=True)
    launch = replace(
        launch,
        config=replace(launch.config, stop_file=tmp_path / "STOP"),
    )
    calls: list[tuple[str, ...]] = []
    backend = SimpleNamespace(label="backend")
    checkpoint = SimpleNamespace(label="checkpoint")
    monkeypatch.setattr(module, "_BACKEND_LOG", tmp_path / "backend.log")
    monkeypatch.setattr(module, "_CHECKPOINT_LOG", tmp_path / "checkpoint.log")
    monkeypatch.setattr(module, "capture_ledger_start", lambda _path: object())
    processes = iter((backend, checkpoint))

    def fake_popen(*_args: object, **_kwargs: object) -> SimpleNamespace:
        process = next(processes)
        calls.append(("start", process.label))
        return process

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        module,
        "_wait_for_backend",
        lambda *_args: calls.append(("ready",)),
    )
    monkeypatch.setattr(
        module,
        "active_ledger_identity",
        lambda _config: SimpleNamespace(run_id="fresh-live-run"),
    )
    monkeypatch.setattr(
        module,
        "_stop_checkpoint_monitor",
        lambda process: calls.append(("checkpoint_stop", process.label)),
    )
    monkeypatch.setattr(
        module, "_stop_owned_backend", lambda *_args: calls.append(("backend_stop",))
    )

    def fake_run(command: tuple[str, ...], *, check: bool) -> SimpleNamespace:
        assert check is False
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.run_supervisor(launch) == 0
    bound_checkpoint = (*launch.checkpoint_command, "--run-id", "fresh-live-run")
    bound_audit = (*launch.audit_command, "--run-id", "fresh-live-run")
    assert calls == [
        ("start", "backend"),
        ("ready",),
        ("start", "checkpoint"),
        launch.tui_command,
        ("checkpoint_stop", "checkpoint"),
        ("backend_stop",),
        (*bound_checkpoint, "--once", "--current-run-only"),
        bound_audit,
    ]


def test_live_supervisor_binds_checkpoints_to_fresh_backend_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new backend cannot inherit the prior checkpoint's run identity."""
    module = _load_module()
    launch = module.resolve_launch(
        module.build_parser().parse_args(
            ["--mode", "live", "--enabled", "--i-accept-live-risk"]
        ),
        credentials_present=True,
    )
    launch = replace(
        launch,
        config=replace(launch.config, stop_file=tmp_path / "STOP"),
    )
    backend = SimpleNamespace(label="backend")
    checkpoint = SimpleNamespace(label="checkpoint")
    checkpoint_commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_BACKEND_LOG", tmp_path / "backend.log")
    monkeypatch.setattr(module, "capture_ledger_start", lambda _path: object())
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: backend)
    monkeypatch.setattr(module, "_wait_for_backend", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "active_ledger_identity",
        lambda _config: SimpleNamespace(run_id="fresh-live-run"),
    )
    monkeypatch.setattr(
        module,
        "_start_checkpoint_monitor",
        lambda command: checkpoint_commands.append(command) or checkpoint,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(module, "_stop_checkpoint_monitor", lambda _process: None)
    monkeypatch.setattr(module, "_stop_owned_backend", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "_publish_final_checkpoint",
        lambda command: checkpoint_commands.append(command) or None,
    )
    monkeypatch.setattr(module, "_publish_audit", lambda _command: None)

    assert module.run_supervisor(launch) == 0
    assert len(checkpoint_commands) == 2
    for command in checkpoint_commands:
        run = command.index("--run-id")
        assert command[run + 1] == "fresh-live-run"
