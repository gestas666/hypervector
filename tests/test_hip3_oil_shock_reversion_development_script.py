"""Report-only CLI boundary for the HIP-3 oil development replay."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


_SCRIPT = Path("scripts/hip3_oil_shock_reversion_development.py")


def _module() -> object:
    assert _SCRIPT.is_file(), "oil development script is missing"
    spec = spec_from_file_location("hip3_oil_development_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    script_directory = str(_SCRIPT.parent.resolve())
    sys.path.insert(0, script_directory)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(script_directory)
    return module


def _report() -> dict[str, object]:
    return {
        "schema_version": "hip3_oil_shock_reversion_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def test_command_publishes_only_zero_authority_evidence(tmp_path: Path) -> None:
    """A development result is immutable and incapable of changing live state."""
    module = _module()
    output = tmp_path / "oil.json"
    args = SimpleNamespace(output=output)

    result = module.run_command(args, report_builder=lambda _args: _report())

    assert result["execution_authority"] == "none"
    assert output.is_file()
    assert result["generator_identity"]["files"]


def test_command_rejects_authority_shaped_report(tmp_path: Path) -> None:
    """An injected live-shaped payload fails before immutable publication."""
    module = _module()
    output = tmp_path / "rejected.json"
    payload = {**_report(), "execution_authority": "live"}

    with pytest.raises(ValueError, match="report-only contract"):
        module.run_command(
            SimpleNamespace(output=output),
            report_builder=lambda _args: payload,
        )

    assert not output.exists()


def test_live_execution_report_supplies_source_bound_stress_floor(
    tmp_path: Path,
) -> None:
    """A Brent canary report contributes its observed slippage tail explicitly."""
    module = _module()
    report = tmp_path / "brent-live.json"
    report.write_text(
        json.dumps(
            {
                "symbol": "xyz:BRENTOIL",
                "execution_authority": "none",
                "lifecycles": [
                    {
                        "entry": {"slippage_bps": -2.5},
                        "exit": {"slippage_bps": 8.46},
                    }
                ],
            }
        )
    )

    floor, observations = module._live_stress_input(
        SimpleNamespace(live_execution_report=report), "xyz:BRENTOIL"
    )

    assert floor == 8.46
    assert observations == 2


def test_parser_exposes_frozen_continuation_mechanism() -> None:
    """The development CLI can select continuation without changing its default."""
    module = _module()
    action = next(
        (item for item in module.build_parser()._actions if item.dest == "mechanism"),
        None,
    )

    assert action is not None
    assert action.default == "reversion"
    assert set(action.choices) == {"reversion", "continuation"}


def test_mechanism_selector_uses_distinct_continuation_evaluator() -> None:
    """The CLI cannot label a reversion replay as continuation evidence."""
    module = _module()
    selector = getattr(module, "_development_evaluator", None)
    assert callable(selector)

    assert selector("continuation").__name__ == (
        "evaluate_hip3_oil_shock_continuation_development"
    )
    assert selector("reversion").__name__ == (
        "evaluate_hip3_oil_shock_reversion_development"
    )
