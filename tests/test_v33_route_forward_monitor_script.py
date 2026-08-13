"""Continuous report-only v33 route-tracking contracts."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v33_route_forward_monitor.py")


def test_once_runs_exact_v33_tracker_and_material_recorder(tmp_path: Path) -> None:
    module = _module()
    commands: list[tuple[str, ...]] = []
    recorded: list[tuple[Path, Path]] = []
    args = module.build_parser().parse_args(
        [
            "--once",
            "--out",
            str(tmp_path / "latest-v33.json"),
            "--change-journal",
            str(tmp_path / "v33-changes.jsonl"),
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
    assert commands[0][1].endswith("scripts/v33_route_forward.py")
    assert str(args.journal).endswith("hip3-route-authority-pruning-v4.json")
    assert str(args.candidate_config).endswith("candidate_v33.toml")
    assert recorded == [(args.out, args.change_journal)]


def _module() -> object:
    spec = spec_from_file_location("v33_route_forward_monitor_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v33 route-forward monitor script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
