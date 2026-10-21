"""Packaged operator tools behind the unified CLI (spec section 10, commit 3).

Covers the new specs (transport spellings, data-root defaults), the in-process
archive backfill and read-only audit, the supervisor's resume dispatch with its
authority rule, and the required arguments that replaced deleted-profile defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import sys

import pytest

from hypervector.cli import main
from hypervector.commands.operations import operation_argv
from hypervector.commands.registry import build_parser, spec_for
from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT

WINDOW = ["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-01T03:00:00Z"]


def _argv(argv: list[str]) -> tuple[str, ...]:
    return operation_argv(build_parser().parse_args(argv))


def _value(command: tuple[str, ...], flag: str) -> str:
    return command[command.index(flag) + 1]


# --- new specs ------------------------------------------------------------


def test_hip3_roster_transports_the_plist_spellings(tmp_path: Path) -> None:
    command = _argv(
        ["--data-root", str(tmp_path), "data", "hip3-roster", "--max-polls", "1"]
    )
    assert command[:3] == (
        sys.executable,
        "-m",
        "hypervector.operations.hip3_roster_observer",
    )
    assert _value(command, "--output") == str(
        tmp_path / "runtime/research/hip3_roster_latest.json"
    )
    assert _value(command, "--poll-seconds") == "120.0"
    assert _value(command, "--context-history") == str(
        tmp_path / "research/hip3_asset_context"
    )
    assert "--out" not in command and "--interval-seconds" not in command


def test_hip3_roster_default_data_root_matches_the_module_defaults() -> None:
    from hypervector.operations.hip3_roster_observer import build_parser as roster

    command = _argv(["data", "hip3-roster"])
    module_defaults = roster().parse_args([])
    parsed = roster().parse_args(list(command[3:]))
    assert parsed.output == module_defaults.output
    assert parsed.context_history == module_defaults.context_history


def test_preflight_requires_both_profiles_and_sends_output() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["live", "preflight", "--config", "c.toml"])
    assert exc.value.code == 2
    command = _argv(
        [
            "live",
            "preflight",
            "--config",
            "c.toml",
            "--active-config",
            "a.toml",
            "--out",
            "report.json",
        ]
    )
    assert _value(command, "--output") == "report.json"
    assert _value(command, "--checkpoint") == (
        "data/runtime/bidirectional_cohort/latest_checkpoint.json"
    )


def test_validate_defaults_to_the_live_mode() -> None:
    command = _argv(["live", "validate", "--config", "c.toml"])
    assert _value(command, "--mode") == "live"


def test_drain_archive_is_a_dry_run_with_data_root_defaults(tmp_path: Path) -> None:
    command = _argv(
        [
            "--data-root",
            str(tmp_path),
            "live",
            "drain-archive",
            "--expected-run-id",
            "run-1",
        ]
    )
    assert "--yes" not in command
    assert _value(command, "--state") == str(
        tmp_path / "live/bidirectional_cohort/transition_drain.json"
    )
    assert _value(command, "--archive-root") == str(
        tmp_path / "backups/bidirectional_cohort/transition_drains"
    )


@pytest.mark.parametrize(
    "command",
    ["live validate", "live backup", "live backup-verify", "live rollback-profile"],
)
def test_transition_tools_refuse_a_foreign_data_root(command: str) -> None:
    assert spec_for(command)["data_root"] == "refused"
    assert spec_for(command)["section"] == "transition"
    assert spec_for(command)["authority"] == "none"


def test_live_help_lists_the_transition_section(capsys) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["live", "--help"])
    out = capsys.readouterr().out
    section = out.split("\ntransition (", 1)[1].split("\n\n", 1)[0]
    for action in (
        "preflight",
        "validate",
        "backup",
        "backup-verify",
        "drain-archive",
        "rollback-profile",
    ):
        assert f"\n  {action} " in section
    assert "resume" in out


# --- live supervisor resume --------------------------------------------------


@pytest.fixture
def resume_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    import hypervector_supervision.cohort_resume_after_reboot as resume

    calls: list[list[str]] = []
    original = resume.main

    def record(argv: list[str] | None = None, **kwargs: object) -> int:
        calls.append(list(argv or []))
        return original(argv, **kwargs)

    monkeypatch.setattr(resume, "main", record)
    monkeypatch.setattr(
        resume, "resume", lambda *_a, **_k: pytest.fail("checks must not run")
    )
    return calls


@pytest.mark.parametrize(
    "flags", [["--yes"], ["--yes", "--enabled"], ["--yes", "--i-accept-live-risk"]]
)
def test_cli_resume_yes_without_both_flags_exits_two(
    flags: list[str], resume_calls: list[list[str]], capsys
) -> None:
    assert main(["live", "supervisor", "resume", *flags]) == 2
    assert resume_calls == [flags]
    assert "requires both --enabled and --i-accept-live-risk" in capsys.readouterr().err


def test_supervisor_dispatches_resume_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    import hypervector_supervision.cohort_backend_supervisor as supervisor
    import hypervector_supervision.cohort_resume_after_reboot as resume

    seen: list[list[str]] = []
    monkeypatch.setattr(resume, "main", lambda argv: seen.append(list(argv)) or 0)
    monkeypatch.setattr(
        supervisor.os, "chdir", lambda _path: pytest.fail("resume must not chdir")
    )
    argv = ["resume", "--yes", "--enabled", "--i-accept-live-risk"]
    assert supervisor.main(argv) == 0
    assert seen == [argv[1:]]


def test_supervisor_help_lists_resume() -> None:
    from hypervector_supervision.cohort_backend_supervisor import build_parser as sup

    assert "resume" in sup().format_help()


def test_resume_helper_text_points_at_the_cli() -> None:
    from hypervector_supervision.cohort_supervisor_runtime import RESUME_HELPER

    from hypervector_supervision.cohort_supervisor_models import REPOSITORY_ROOT

    assert RESUME_HELPER == (
        f"{REPOSITORY_ROOT / '.venv' / 'bin' / 'python'} -m hypervector "
        "live supervisor resume"
    )


def test_resume_module_imports_nothing_from_hypervector() -> None:
    source = (
        REPOSITORY_ROOT / "src/hypervector_supervision/cohort_resume_after_reboot.py"
    ).read_text()
    imported = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", source, flags=re.M)
    assert "hypervector_supervision.cohort_supervisor_health" in imported
    assert not [name for name in imported if name.split(".")[0] == "hypervector"]


# --- required arguments that replaced deleted-profile defaults ---------------


@pytest.mark.parametrize(
    ("module", "argv"),
    [
        ("hypervector.operations.multi_asset_bidirectional_preflight", []),
        (
            "hypervector.operations.multi_asset_bidirectional_preflight",
            ["--config", "c.toml"],
        ),
        ("hypervector.operations.cohort_prechange_backup", []),
        ("hypervector.operations.multi_asset_bidirectional_observe", []),
        ("hypervector.operations.multi_asset_bidirectional_live_checkpoint", []),
    ],
)
def test_deleted_profile_defaults_are_now_required(
    module: str, argv: list[str]
) -> None:
    from importlib import import_module

    with pytest.raises(SystemExit) as exc:
        import_module(module).build_parser().parse_args(argv)
    assert exc.value.code == 2


def test_validation_passes_the_requested_mode_to_the_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hypervector.operations.cohort_runtime_validation_check as check

    seen: list[str] = []

    def fake_check(_path: Path, *, mode: str) -> list[str]:
        seen.append(mode)
        return []

    monkeypatch.setattr(check, "check", fake_check)
    assert check.main(["--config", str(tmp_path / "p.toml"), "--mode", "observe"]) == 0
    assert seen == ["observe"]


def test_rollback_profile_root_defaults_to_the_repository(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import hypervector.operations.cohort_rollback_profile as rollback

    directories: list[Path] = []
    monkeypatch.setattr(rollback.os, "chdir", directories.append)

    def refuse(_args: object) -> dict[str, object]:
        raise rollback.RollbackProfileError("stop after chdir")

    monkeypatch.setattr(rollback, "verify_rollback", refuse)
    assert rollback.main(["--current", "a.toml", "--verify", "b.toml"]) == 2
    assert directories == [REPOSITORY_ROOT]
    assert "stop after chdir" in capsys.readouterr().err


# --- archive backfill (in-process) ------------------------------------------


@dataclass(frozen=True)
class _Task:
    kind: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class _Result:
    task: _Task
    rows: int
    pages: int
    skipped: bool


def test_archive_backfill_runs_the_packaged_job_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import hypervector.operations.oxa_backfill as backfill

    seen: dict[str, object] = {}
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def fake_run(config, *, api_key: str, progress):
        seen["config"] = config
        result = _Result(_Task("book", start, start + timedelta(hours=1)), 5, 1, False)
        progress(result)
        return (result,)

    monkeypatch.setattr(backfill, "run_oxa_backfill", fake_run)
    argv = [
        "--data-root",
        str(tmp_path),
        "archive",
        "backfill",
        "--symbol",
        "ETH",
        *WINDOW,
        "--chunk-minutes",
        "30",
        "--workers",
        "2",
        "--books-only",
    ]
    assert main(argv) == 0
    config = seen["config"]
    assert config.symbol == "ETH"
    assert config.data_root == tmp_path
    assert config.chunk == timedelta(minutes=30)
    assert (config.workers, config.retries) == (2, 10)
    assert config.book_only is True and config.price_only is False
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["status"] == "downloaded" and lines[0]["rows"] == 5
    assert lines[-1] == {"ok": True, "tasks": 1, "rows": 5, "pages": 1}


def test_archive_backfill_failure_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import hypervector.operations.oxa_backfill as backfill

    def broken(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        raise RuntimeError("window incomplete after retries")

    monkeypatch.setattr(backfill, "run_oxa_backfill", broken)
    argv = ["--data-root", str(tmp_path), "archive", "backfill", *WINDOW]
    assert main(argv) == 1
    assert "window incomplete after retries" in capsys.readouterr().err


# --- archive audit (read-only) ---------------------------------------------


def _audit(tmp_path: Path, *extra: str) -> tuple[int, dict[str, object]]:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["--data-root", str(tmp_path), "archive", "audit", *WINDOW, *extra])
    return code, json.loads(buffer.getvalue()) if buffer.getvalue() else {}


def test_archive_audit_reports_every_missing_hour_without_creating_anything(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    code, report = _audit(root)
    assert code == 0
    assert report["complete"] is False
    assert (report["expected"], report["present"]) == (6, 0)
    assert report["missing"] == [
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T01:00:00+00:00",
        "2026-01-01T02:00:00+00:00",
    ]
    assert len(report["missing_directories"]) == 6
    assert report["read_only"] is True
    assert not root.exists()


def test_archive_audit_books_only_expects_one_bundle_per_hour(tmp_path: Path) -> None:
    code, report = _audit(tmp_path / "data", "--books-only")
    assert code == 0
    assert (report["expected"], report["present"]) == (3, 0)


def test_archive_audit_lists_only_the_incomplete_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hypervector.data.oxa_archive_audit as audit

    real = audit.audit_oxa_archive
    seen: list[datetime] = []

    def partial(config):
        seen.append(config.start)
        report = real(config)
        if config.start.hour == 1:
            return report
        return type(report)(
            **{
                **report.to_dict(),
                "complete": True,
                "present_bundles": report.expected_bundles,
                "missing_directories": (),
                "book_snapshots": 10,
            }
        )

    monkeypatch.setattr(audit, "audit_oxa_archive", partial)
    code, report = _audit(tmp_path / "data")
    assert code == 0
    assert len(seen) == 3
    assert report["missing"] == ["2026-01-01T01:00:00+00:00"]
    assert (report["expected"], report["present"]) == (6, 4)
    assert report["book_snapshots"] == 20
    assert report["complete"] is False


@pytest.mark.parametrize(
    "extra",
    [["--symbol", "not a symbol!"], ["--chunk-minutes", "0"]],
)
def test_archive_audit_invalid_scope_is_refused(
    tmp_path: Path, extra: list[str], capsys
) -> None:
    code, _report = _audit(tmp_path / "data", *extra)
    assert code == 2
    assert json.loads(capsys.readouterr().err)["command"] == "archive audit"
