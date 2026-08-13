"""Publication boundary for immutable v43 technical acceptance."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v43_poststart_acceptance.py")


def test_report_binds_every_input_and_rejects_later_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Acceptance cannot publish after any frozen input changes."""
    script = _module()
    paths = _inputs(tmp_path)
    monkeypatch.setattr(script, "build_v43_poststart_acceptance", _fake_build)
    args = argparse.Namespace(
        checkpoint=paths["checkpoint"],
        config=paths["config"],
        risk=paths["risk"],
        preflight=paths["preflight"],
        out=tmp_path / "acceptance.json",
        maximum_checkpoint_age_seconds=90.0,
        maximum_pressure_age_seconds=30.0,
    )

    report = script.run_report(args)

    assert report["accepted"] is True
    assert set(report["evidence"]) == {"checkpoint", "config", "risk", "preflight"}
    script.require_unchanged_inputs(report)
    paths["risk"].write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="input changed"):
        script.require_unchanged_inputs(report)


def test_output_cannot_alias_an_input(tmp_path: Path) -> None:
    """Publication must not overwrite any evidence source."""
    script = _module()
    paths = _inputs(tmp_path)
    args = argparse.Namespace(
        checkpoint=paths["checkpoint"],
        config=paths["config"],
        risk=paths["risk"],
        preflight=paths["preflight"],
        out=paths["risk"],
        maximum_checkpoint_age_seconds=90.0,
        maximum_pressure_age_seconds=30.0,
    )

    with pytest.raises(ValueError, match="output must differ"):
        script.run_report(args)


def _inputs(root: Path) -> dict[str, Path]:
    paths = {
        name: root / f"{name}.json" for name in ("checkpoint", "risk", "preflight")
    }
    paths["config"] = Path(
        "configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml"
    )
    for name, path in paths.items():
        if name == "config":
            continue
        path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
    return paths


def _fake_build(*args: object, **kwargs: object) -> dict[str, object]:
    assert kwargs["maximum_checkpoint_age_seconds"] == 90.0
    assert kwargs["maximum_pressure_age_seconds"] == 30.0
    return {"accepted": True, "decision": "accepted", "reasons": []}


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v43 post-start acceptance script is missing")
    spec = spec_from_file_location("v43_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v43 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
