"""CLI contracts for the continuous report-only v31 route tracker."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v31_route_forward_monitor.py")


def test_once_runs_exact_report_only_tracker_command() -> None:
    module = _module()
    commands: list[tuple[str, ...]] = []
    args = module.build_parser().parse_args(["--once"])

    result = module.run_monitor(
        args,
        run_cycle=lambda command: commands.append(tuple(command)) or 0,
        sleep_fn=lambda _: pytest.fail("once mode must not sleep"),
    )

    assert result == 0
    assert len(commands) == 1
    assert commands[0][1].endswith("scripts/v31_route_forward.py")
    assert "--immutable" not in commands[0]


def test_monitor_retries_failed_refresh_without_claiming_success() -> None:
    module = _module()
    exits = iter([2, 0])
    sleeps: list[float] = []
    args = module.build_parser().parse_args(
        ["--interval-seconds", "7", "--max-cycles", "2"]
    )

    result = module.run_monitor(
        args,
        run_cycle=lambda _: next(exits),
        sleep_fn=sleeps.append,
    )

    assert result == 2
    assert sleeps == [7.0]


def test_monitor_records_only_successful_material_refreshes(tmp_path: Path) -> None:
    """Failed snapshots must not enter the durable material-change journal."""
    module = _module()
    exits = iter([2, 0])
    recorded: list[tuple[Path, Path]] = []
    args = module.build_parser().parse_args(
        [
            "--interval-seconds",
            "1",
            "--max-cycles",
            "2",
            "--out",
            str(tmp_path / "latest.json"),
            "--change-journal",
            str(tmp_path / "changes.jsonl"),
        ]
    )

    result = module.run_monitor(
        args,
        run_cycle=lambda _: next(exits),
        sleep_fn=lambda _: None,
        record_change=lambda snapshot, journal: recorded.append((snapshot, journal))
        or True,
    )

    assert result == 2
    assert recorded == [(args.out, args.change_journal)]


def test_monitor_forwards_identity_bound_paths(tmp_path: Path) -> None:
    module = _module()
    args = module.build_parser().parse_args(
        [
            "--once",
            "--checkpoint",
            str(tmp_path / "checkpoint.json"),
            "--journal",
            str(tmp_path / "journal.json"),
            "--source-config",
            str(tmp_path / "v25.toml"),
            "--candidate-config",
            str(tmp_path / "v31.toml"),
            "--out",
            str(tmp_path / "latest.json"),
        ]
    )

    command = module.tracker_command(args)

    assert command[-10:] == [
        "--checkpoint",
        str(tmp_path / "checkpoint.json"),
        "--journal",
        str(tmp_path / "journal.json"),
        "--source-config",
        str(tmp_path / "v25.toml"),
        "--candidate-config",
        str(tmp_path / "v31.toml"),
        "--out",
        str(tmp_path / "latest.json"),
    ]


def test_monitor_rejects_nonpositive_interval() -> None:
    module = _module()
    args = module.build_parser().parse_args(["--interval-seconds", "0"])

    with pytest.raises(ValueError, match="interval must be positive"):
        module.run_monitor(args, run_cycle=lambda _: 0, sleep_fn=lambda _: None)


def _module() -> argparse.Namespace:
    spec = spec_from_file_location("v31_route_forward_monitor_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v31 route-forward monitor script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
