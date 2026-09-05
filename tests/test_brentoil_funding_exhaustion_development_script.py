"""Report-only CLI boundary for the BRENTOIL exhaustion screen."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

_SCRIPT = Path("scripts/brentoil_funding_price_exhaustion_development.py")


def _module() -> object:
    assert _SCRIPT.is_file(), "BRENTOIL exhaustion script is missing"
    spec = spec_from_file_location("brentoil_funding_exhaustion_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent.resolve()))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "validation_accessed": False,
            "holdout_accessed": False,
        },
    }


def test_command_publishes_only_zero_authority_evidence(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "brent.json"

    result = module.run_command(
        SimpleNamespace(output=output), report_builder=lambda _args: _report()
    )

    assert output.is_file()
    assert result["contract"]["execution_authority"] == "none"
    assert result["generator_identity"]["files"]


def test_command_rejects_live_shaped_report(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "rejected.json"
    report = _report()
    report["contract"] = {**report["contract"], "execution_authority": "live"}

    with pytest.raises(ValueError, match="report-only contract"):
        module.run_command(
            SimpleNamespace(output=output), report_builder=lambda _args: report
        )

    assert not output.exists()


def test_command_refuses_existing_immutable_output(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "existing.json"
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.run_command(
            SimpleNamespace(output=output), report_builder=lambda _args: _report()
        )
