"""V95 stays restartable after the CLI unification (spec section 7.8 and 10.1).

Pins what a same-profile restart depends on: the three profile fingerprints, the
byte-identical launchd entry scripts, the hashed live entrypoint, and the argv of
every installed LaunchAgent, which must still parse with the module parsers the
shims now point at. Nothing here starts, arms or kickstarts anything; the plist
argument lists are embedded literally (read once from the installed agents) so
the tests never depend on the host's LaunchAgents directory.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from hypervector.commands.operations import operation_argv
from hypervector.commands.registry import build_parser as build_cli_parser
from hypervector.live.cohort_implementation_sources import (
    _ENTRYPOINT,
    discover_cohort_implementation_sources,
)
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector_supervision.cohort_supervisor_health import _backend_command
from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT

REPO = Path(__file__).resolve().parents[1]
V95 = "configs/multi_asset_growth_first_5000_review_fixes_v95.toml"
V94 = "configs/multi_asset_growth_first_5000_review_actions_v94.toml"
ROLLBACK = "configs/v95-to-v94-rollback-20260927-v1.toml"
FINGERPRINTS = {
    V95: "dd779cce74568e4ba6963d1a19810a7fbcaa7f4279e40f45be83f12286339420",
    V94: "930117e9ac0f4bb91fc66631666f47eb68a5d66bd8928684d8792f63122b3fd1",
    ROLLBACK: "5fe5a9de14b4ae7b7ab7e53cea7dd6c8bc6a2341f851b2d76f5b0e158a6c7beb",
}
# Byte-identical launchd and hashed-entrypoint targets (spec invariant 1.4).
PINNED_SCRIPTS = {
    "scripts/cohort_backend_supervisor.py": (
        "0b11e4af17f3b4ac2cdc00d2d17a3927abc8b3f40af56303d6acc70a963bcae5"
    ),
    "scripts/multi_asset_bidirectional_live.py": (
        "b973fdf319f8d630569d02bdb30439125dccf2b1b4e27f0690f9a19c8d4cd2dd"
    ),
    "scripts/multi_asset_bidirectional_live_checkpoint.py": (
        "9ae88fd4de86d9cdb300ba14a83d271446e51abeb38c15503aa0a8a9d5151e23"
    ),
}
_PY = "/Users/gestas/Prototypes/hypervector/.venv/bin/python"
_ROOT = "/Users/gestas/Prototypes/hypervector"
# ProgramArguments of the installed local.hypervector.* agents (WorkingDirectory
# is the repository root for all four).
PLIST_CHECKPOINT = [
    _PY,
    "-u",
    f"{_ROOT}/scripts/multi_asset_bidirectional_live_checkpoint.py",
    "--ledger-root",
    "data/live/bidirectional_cohort",
    "--out",
    "data/runtime/bidirectional_cohort/latest_checkpoint.json",
    "--config",
    V95,
    "--research-database",
    "data/research/market.duckdb",
    "--research-sync-interval-seconds",
    "120",
    "--venue-portfolio",
    "--current-run-only",
    "--disable-asymmetric-forward-observer",
    "--follow-latest-run",
]
PLIST_SUPERVISE = [
    _PY,
    f"{_ROOT}/scripts/cohort_backend_supervisor.py",
    "supervise",
    "--interval",
    "30",
    "--",
    _PY,
    "-u",
    "scripts/multi_asset_bidirectional_live.py",
    "--config",
    V95,
    "--enabled",
    "--i-accept-live-risk",
]
PLIST_WATCH = [
    _PY,
    f"{_ROOT}/scripts/cohort_backend_supervisor.py",
    "watch",
    "--interval",
    "30",
]
PLIST_ROSTER = [
    _PY,
    "-u",
    f"{_ROOT}/scripts/hip3_roster_observer.py",
    "--output",
    f"{_ROOT}/data/runtime/research/hip3_roster_latest.json",
    "--poll-seconds",
    "120",
    "--context-history",
    f"{_ROOT}/data/research/hip3_asset_context",
]
SHIMS = {
    "multi_asset_bidirectional_preflight": "hypervector.operations",
    "cohort_runtime_validation_check": "hypervector.operations",
    "cohort_rollback_profile": "hypervector.operations",
    "cohort_transition_drain_archive": "hypervector.operations",
    "cohort_prestart_backup_verify": "hypervector.operations",
    "cohort_prechange_backup": "hypervector.operations",
    "hip3_roster_observer": "hypervector.operations",
    "oxa_backfill": "hypervector.operations",
    "cohort_resume_after_reboot": "hypervector_supervision",
    "multi_asset_bidirectional_live": "hypervector.operations",
    "multi_asset_bidirectional_live_checkpoint": "hypervector.operations",
    "cohort_backend_supervisor": "hypervector_supervision",
}
_IMPORT = re.compile(r'import_module\("([\w.]+)"\)')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _script_target(script: str) -> str:
    """The packaged module a shim (or pinned alias) script replaces itself with."""
    [target] = _IMPORT.findall((REPO / "scripts" / Path(script).name).read_text())
    return target


@pytest.mark.parametrize(("path", "fingerprint"), FINGERPRINTS.items())
def test_profile_fingerprints_are_pinned_and_load_in_observe_mode(
    path: str, fingerprint: str
) -> None:
    config = load_multi_asset_live_config(REPO / path, mode="observe")
    assert config.profile_fingerprint == fingerprint


@pytest.mark.parametrize(("path", "digest"), PINNED_SCRIPTS.items())
def test_launchd_entry_scripts_are_byte_identical(path: str, digest: str) -> None:
    assert _sha256(REPO / path) == digest


def test_the_hashed_live_entrypoint_exists() -> None:
    assert (REPO / _ENTRYPOINT).is_file()
    assert _script_target(str(_ENTRYPOINT)) == (
        "hypervector.operations.multi_asset_bidirectional_live"
    )


def test_checkpoint_plist_argv_parses_with_the_module_parser() -> None:
    from hypervector.operations.multi_asset_bidirectional_live_checkpoint import (
        build_parser,
    )

    script = PLIST_CHECKPOINT[2]
    assert _script_target(script) == (
        "hypervector.operations.multi_asset_bidirectional_live_checkpoint"
    )
    args = build_parser().parse_args(PLIST_CHECKPOINT[3:])
    assert args.config == Path(V95)
    assert args.current_run_only is True
    assert args.disable_asymmetric_forward_observer is True
    assert args.asymmetric_forward_journal is None
    assert args.follow_latest_run is True
    assert args.venue_portfolio is True
    assert args.research_sync_interval_seconds == 120.0


def test_supervise_plist_argv_parses_and_names_the_armed_v95_backend() -> None:
    from hypervector.operations.multi_asset_bidirectional_live import (
        build_parser as backend_parser,
    )
    from hypervector_supervision.cohort_backend_supervisor import build_parser

    assert _script_target(PLIST_SUPERVISE[1]) == (
        "hypervector_supervision.cohort_backend_supervisor"
    )
    args = build_parser().parse_args(PLIST_SUPERVISE[2:])
    assert args.command == "supervise"
    assert args.interval == 30.0
    child = args.child[1:] if args.child[:1] == ["--"] else args.child
    assert child[2] == str(_ENTRYPOINT)
    assert _backend_command(child)
    backend = backend_parser().parse_args(child[3:])
    assert backend.config == Path(V95)
    assert backend.enabled is True and backend.i_accept_live_risk is True


def test_watch_plist_argv_parses_with_the_supervisor_parser() -> None:
    from hypervector_supervision.cohort_backend_supervisor import build_parser

    args = build_parser().parse_args(PLIST_WATCH[2:])
    assert (args.command, args.interval) == ("watch", 30.0)


def test_roster_plist_argv_parses_with_the_packaged_observer() -> None:
    from hypervector.operations.hip3_roster_observer import (
        build_parser,
        config_from_args,
    )

    assert _script_target(PLIST_ROSTER[2]) == (
        "hypervector.operations.hip3_roster_observer"
    )
    config = config_from_args(build_parser().parse_args(PLIST_ROSTER[3:]))
    assert config.output == Path(PLIST_ROSTER[4])
    assert config.poll_seconds == 120.0
    assert config.context_history == Path(PLIST_ROSTER[8])
    assert config.max_polls is None


@pytest.mark.parametrize(("name", "package"), SHIMS.items())
def test_every_script_shim_runs_help(name: str, package: str, tmp_path: Path) -> None:
    """Each shim resolves its packaged module from this checkout and exits 0."""
    script = REPO / "scripts" / f"{name}.py"
    assert _script_target(script.name) == f"{package}.{name}"
    environment = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_new_shims_are_nine_lines() -> None:
    for name in list(SHIMS)[:9]:
        lines = (REPO / "scripts" / f"{name}.py").read_text().splitlines()
        assert len(lines) == 9, name


def test_live_backup_discovers_the_live_entrypoint_role_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'live backup' binds the same implementation sources a live start does."""
    import hypervector.operations.cohort_prechange_backup as backup

    provider = tmp_path / "backtest_lab"
    provider.mkdir()
    (provider / "__init__.py").write_text('"""fixture provider"""\n')
    captured: dict[str, object] = {}

    def create(_config: object, *, implementation_sources: object) -> object:
        captured["sources"] = implementation_sources
        raise CohortPrestartBackupError("stop after discovery")

    monkeypatch.setattr(
        backup,
        "load_multi_asset_live_config",
        lambda path, *, mode: SimpleNamespace(profile_id="v", profile_fingerprint="f"),
    )
    monkeypatch.setattr(backup, "create_cohort_prestart_backup", create)
    argv = ["--config", V95, "--backtest-lab-root", str(provider)]
    assert backup.main(argv) == 2
    expected = discover_cohort_implementation_sources(REPOSITORY_ROOT, provider)
    assert captured["sources"] == expected
    values = set(expected.values())
    assert (REPOSITORY_ROOT / _ENTRYPOINT).resolve() in values
    assert (
        REPOSITORY_ROOT / "src/hypervector/operations/cohort_prechange_backup.py"
    ).resolve() in values
    assert (
        REPOSITORY_ROOT / "src/hypervector_supervision/cohort_resume_after_reboot.py"
    ).resolve() in values


@pytest.mark.parametrize(
    ("argv", "module", "transported"),
    [
        (
            ["live", "validate", "--config", V95, "--mode", "live", "--equity", "5000"],
            "hypervector.operations.cohort_runtime_validation_check",
            ["--config", V95, "--mode", "live", "--equity", "5000.0"],
        ),
        (
            ["live", "backup", "--config", V95],
            "hypervector.operations.cohort_prechange_backup",
            ["--config", V95, "--backtest-lab-root", "../backtest-lab/backtest_lab"],
        ),
        (
            ["live", "backup-verify", "--bundle", "bundle-dir"],
            "hypervector.operations.cohort_prestart_backup_verify",
            ["--bundle", "bundle-dir"],
        ),
    ],
)
def test_offline_rehearsal_commands_map_to_the_packaged_tools(
    argv: list[str], module: str, transported: list[str]
) -> None:
    """The V95 rehearsal (section 7.8) needs no authority and starts nothing."""
    command = operation_argv(build_cli_parser().parse_args(argv))
    assert command[:3] == (sys.executable, "-m", module)
    assert list(command[3:]) == transported
    assert "--enabled" not in command and "--i-accept-live-risk" not in command
