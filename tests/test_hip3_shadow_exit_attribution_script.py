"""Immutable command tests for HIP-3 exit attribution."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


def _script() -> ModuleType:
    path = Path("scripts/hip3_shadow_exit_attribution.py")
    spec = importlib.util.spec_from_file_location("hip3_exit_attribution_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HIP-3 exit-attribution script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _args(script: ModuleType, tmp_path: Path) -> object:
    lifecycle = tmp_path / "lifecycle.json"
    markouts = tmp_path / "markouts.json"
    lifecycle.write_text(json.dumps({"source": "lifecycle"}), encoding="utf-8")
    markouts.write_text(json.dumps({"source": "markouts"}), encoding="utf-8")
    return script.build_parser().parse_args(
        [
            "--lifecycle-report",
            str(lifecycle),
            "--markout-report",
            str(markouts),
            "--output",
            str(tmp_path / "attribution.json"),
        ]
    )


def _report() -> dict[str, object]:
    return {
        "schema_version": "hip3_shadow_exit_attribution_v1",
        "symbol": "xyz:MU",
        "provider_id": "hip3_mu_breakout_shadow_preclose_v1",
        "profile_id": "mu_hip3_breakout_shadow_preclose_v1",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "summary": {"completed_lifecycles": 1},
    }


def test_command_publishes_hash_bound_authority_none_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both inputs and generator bytes are frozen before immutable publication."""
    script = _script()
    args = _args(script, tmp_path)
    monkeypatch.setattr(
        script, "build_hip3_shadow_exit_attribution", lambda *_: _report()
    )

    report = script.run_command(args)

    persisted = json.loads(Path(args.output).read_text())
    assert report == persisted
    assert persisted["execution_authority"] == "none"
    assert persisted["input_evidence"]["lifecycle_report"]["sha256"]
    assert persisted["input_evidence"]["markout_report"]["sha256"]
    assert set(persisted["generator_identity"]) == {
        "scripts/hip3_shadow_exit_attribution.py",
        "src/hypervector/research/hip3_shadow_exit_attribution.py",
    }


def test_command_aborts_if_an_input_changes_during_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent evidence mutation cannot publish a mixed-revision artifact."""
    script = _script()
    args = _args(script, tmp_path)

    def mutate(*_values: object) -> dict[str, object]:
        Path(args.markout_report).write_text('{"changed": true}', encoding="utf-8")
        return _report()

    monkeypatch.setattr(script, "build_hip3_shadow_exit_attribution", mutate)

    with pytest.raises(ValueError, match="changed during evaluation"):
        script.run_command(args)
    assert not Path(args.output).exists()


def test_command_rejects_existing_or_aliased_output_before_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publication is append-once and output cannot alias an evidence input."""
    script = _script()
    args = _args(script, tmp_path)
    called = False

    def build(*_values: object) -> dict[str, object]:
        nonlocal called
        called = True
        return _report()

    monkeypatch.setattr(script, "build_hip3_shadow_exit_attribution", build)
    Path(args.output).write_text("reserved", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        script.run_command(args)
    assert called is False

    Path(args.output).unlink()
    args.output = args.lifecycle_report
    with pytest.raises(ValueError, match="distinct"):
        script.run_command(args)
    assert called is False
