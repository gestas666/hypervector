"""CLI contracts for continuous report-only v32 route tracking."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from hypervector.research.route_forward_monitor import record_material_change

_SCRIPT = Path("scripts/v32_route_forward_monitor.py")


def test_once_runs_exact_v32_tracker_and_material_recorder(tmp_path: Path) -> None:
    module = _module()
    commands: list[tuple[str, ...]] = []
    recorded: list[tuple[Path, Path]] = []
    args = module.build_parser().parse_args(
        [
            "--once",
            "--out",
            str(tmp_path / "latest-v32.json"),
            "--change-journal",
            str(tmp_path / "v32-changes.jsonl"),
        ]
    )

    result = module.run_monitor(
        args,
        run_cycle=lambda command: commands.append(tuple(command)) or 0,
        sleep_fn=lambda _: pytest.fail("once mode must not sleep"),
        record_change=lambda snapshot, journal: recorded.append((snapshot, journal))
        or True,
    )

    assert result == 0
    assert commands[0][1].endswith("scripts/v32_route_forward.py")
    assert str(args.journal).endswith("hip3-route-authority-pruning-v3.json")
    assert str(args.candidate_config).endswith("candidate_v32.toml")
    assert recorded == [(args.out, args.change_journal)]


def test_monitor_retains_failed_cycle_status() -> None:
    module = _module()
    exits = iter([2, 0])
    args = module.build_parser().parse_args(
        ["--interval-seconds", "1", "--max-cycles", "2"]
    )

    result = module.run_monitor(
        args,
        run_cycle=lambda _: next(exits),
        sleep_fn=lambda _: None,
    )

    assert result == 2


def test_material_recorder_loads_snapshot_before_append(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    journal = tmp_path / "changes.jsonl"
    snapshot.write_text('{"schema_version":"v32"}\n', encoding="utf-8")
    captured: list[tuple[Path, object]] = []

    result = record_material_change(
        snapshot,
        journal,
        appender=lambda path, payload: captured.append((path, payload)) or True,
    )

    assert result is True
    assert captured == [(journal, {"schema_version": "v32"})]


def _module() -> argparse.Namespace:
    spec = spec_from_file_location("v32_route_forward_monitor_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v32 route-forward monitor script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
