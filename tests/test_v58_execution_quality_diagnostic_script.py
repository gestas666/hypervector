"""Immutable CLI coverage for the V58 execution-quality diagnosis."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


def test_publisher_freezes_checkpoint_and_remains_report_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publication must be immutable and preserve authority-none evidence."""
    module = _script_module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"checkpoint":"fixture"}\n', encoding="utf-8")
    generator = tmp_path / "generator.py"
    generator.write_text("# fixture\n", encoding="utf-8")
    output = tmp_path / "report.json"
    expected = {
        "mode": "report_only_current_run_diagnostic",
        "contract": {"execution_authority": "none"},
    }
    monkeypatch.setattr(module, "_generator_paths", lambda: (generator,))
    monkeypatch.setattr(
        module,
        "build_v58_execution_quality_diagnostic",
        lambda payload: {**expected, "input_payload": payload},
    )
    args = argparse.Namespace(checkpoint=checkpoint, out=output)

    report = module.publish_report(args)

    assert report["contract"]["execution_authority"] == "none"
    assert report["source_evidence"]["checkpoint"]["path"] == str(checkpoint.resolve())
    assert report["source_checkpoint_snapshot"] == {"checkpoint": "fixture"}
    assert report["generator_identity"][0]["path"] == str(generator.resolve())
    assert json.loads(output.read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(args)


def test_generator_identity_covers_diagnostic_and_storage() -> None:
    """Modules capable of changing report bytes must be source-bound."""
    module = _script_module()

    names = {path.name for path in module._generator_paths()}

    assert "v58_execution_quality_diagnostic.py" in names
    assert "oxa_storage.py" in names
    assert "hip3_development_provenance.py" in names


def _script_module() -> object:
    script = Path("scripts/v58_execution_quality_diagnostic.py")
    spec = importlib.util.spec_from_file_location("v58_execution_diagnostic", script)
    assert spec is not None and spec.loader is not None, "V58 diagnostic CLI missing"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
