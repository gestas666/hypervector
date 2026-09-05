"""Tests for immutable V62 all-route stop diagnostic publication."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "v62_route_stop_diagnostic.py"


def _load() -> object:
    spec = spec_from_file_location("v62_route_stop_diagnostic_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V62 route diagnostic script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_binds_config_checkpoint_and_authority_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must remain immutable and execution-incapable."""
    config = tmp_path / "profile.toml"
    checkpoint = tmp_path / "checkpoint.json"
    config.write_text('profile = "v61"\nproviders = []\n')
    checkpoint.write_text('{"generated_at_utc":"2026-08-25T17:00:00Z"}')
    script = _load()
    expected = {"summary": {"executable_routes": 10}}
    monkeypatch.setattr(
        script, "build_route_stop_diagnostic", lambda config, checkpoint: expected
    )
    monkeypatch.setattr(
        script,
        "file_evidence",
        lambda path: {"sha256": f"sha-{path.name}", "bytes": path.stat().st_size},
    )

    report = script.run(SimpleNamespace(config=config, checkpoint=checkpoint))

    assert report["diagnostic"] == expected
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["sources"]["config"]["sha256"] == "sha-profile.toml"
