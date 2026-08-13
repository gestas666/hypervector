"""Publication boundary for immutable v44 technical acceptance."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v44_poststart_acceptance.py")


def test_report_binds_all_five_inputs_and_rejects_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The verifier cannot publish after any evidence byte changes."""
    script = _module()
    paths = _inputs(tmp_path)
    monkeypatch.setattr(script, "build_v44_poststart_acceptance", _fake_build)
    args = _args(paths, tmp_path / "acceptance.json")

    report = script.run_report(args)

    assert set(report["evidence"]) == {
        "checkpoint",
        "config",
        "risk",
        "friction",
        "preflight",
    }
    script.require_unchanged_inputs(report)
    paths["friction"].write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="input changed"):
        script.require_unchanged_inputs(report)


def test_output_cannot_alias_a_v44_input(tmp_path: Path) -> None:
    """Publication cannot overwrite a frozen input."""
    script = _module()
    paths = _inputs(tmp_path)
    with pytest.raises(ValueError, match="output must differ"):
        script.run_report(_args(paths, paths["risk"]))


def _args(paths: dict[str, Path], output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        checkpoint=paths["checkpoint"],
        config=paths["config"],
        risk=paths["risk"],
        friction=paths["friction"],
        preflight=paths["preflight"],
        out=output,
        maximum_checkpoint_age_seconds=90.0,
        maximum_pressure_age_seconds=30.0,
    )


def _inputs(root: Path) -> dict[str, Path]:
    paths = {
        name: root / f"{name}.json"
        for name in ("checkpoint", "risk", "friction", "preflight")
    }
    paths["config"] = Path(
        "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
    )
    for name, path in paths.items():
        if name != "config":
            path.write_text(json.dumps({"name": name}) + "\n", encoding="utf-8")
    return paths


def _fake_build(*args: object, **kwargs: object) -> dict[str, object]:
    assert kwargs["maximum_checkpoint_age_seconds"] == 90.0
    assert kwargs["maximum_pressure_age_seconds"] == 30.0
    return {"accepted": True, "decision": "accepted", "reasons": []}


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v44 post-start acceptance script is missing")
    spec = spec_from_file_location("v44_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v44 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
