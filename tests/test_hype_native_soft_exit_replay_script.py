"""Command-surface tests for the HYPE native soft-exit replay."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_soft_exit_replay.py")


def test_command_writes_one_immutable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must preserve report-only inputs and refuse replacement."""
    module = _load_script()
    output = tmp_path / "result.json"
    observed: dict[str, object] = {}

    def fake_report(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"authority": "none", "decision": {"outcome": "extend"}}

    monkeypatch.setattr(module, "build_hype_native_soft_exit_report", fake_report)
    arguments = [
        "--config",
        "candidate.toml",
        "--ledger",
        "candidate.jsonl",
        "--opened-at-ms",
        "1000",
        "--observed-ms",
        "2000",
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    assert observed == {
        "config_path": Path("candidate.toml"),
        "ledger_path": Path("candidate.jsonl"),
        "opened_at_ms": 1000,
        "observed_ms": 2000,
    }
    assert json.loads(output.read_text(encoding="utf-8"))["authority"] == "none"
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.main(arguments)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "hype_native_soft_exit_replay", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load HYPE native soft-exit replay script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
