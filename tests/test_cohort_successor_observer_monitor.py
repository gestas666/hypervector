"""Integration regression for V58 evidence in the improvement monitor."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_FIXTURES = Path(__file__).with_name("test_cohort_improvement_monitor_script.py")


def test_refresh_attaches_v58_successor_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The moving digest must expose the isolated V58 observer explicitly."""
    fixtures = _load(_FIXTURES, "improvement_monitor_fixtures")
    module = fixtures._load()
    checkpoint, output, history, overrides, _ = fixtures._monitor_files(tmp_path)
    fixtures._install_fakes(module, monkeypatch)
    successor = SimpleNamespace(
        status={"profile_id": "v58", "execution_authority": "none"},
        evidence={"sha256": "observer-source"},
    )
    monkeypatch.setattr(
        module.v58,
        "load_v58_successor_observer_for_profile",
        lambda audit, observed_at: successor,
    )
    args = fixtures._once_args(module, checkpoint, output, history, overrides)

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    persisted = json.loads(output.read_text())
    assert persisted["successor_observer"] == successor.status
    assert persisted["evidence"]["successor_observer"] == successor.evidence


def _load(path: Path, name: str) -> ModuleType:
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load test fixture module: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
