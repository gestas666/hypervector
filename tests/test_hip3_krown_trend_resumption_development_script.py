"""Report-only command boundary for the BRENTOIL Krown development replay."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution


_SCRIPT = Path("scripts/hip3_krown_trend_resumption_development.py")


def _module() -> object:
    """Load the script without invoking its CLI entry point."""
    assert _SCRIPT.is_file(), "Krown development script is missing"
    spec = spec_from_file_location("hip3_krown_development_script", _SCRIPT)
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
    """Return the minimal valid zero-authority report shape."""
    return {
        "schema_version": "hip3_krown_trend_resumption_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def test_command_publishes_only_immutable_zero_authority_evidence(
    tmp_path: Path,
) -> None:
    """A development result must not create a live-shaped side effect."""
    module = _module()
    output = tmp_path / "krown.json"

    result = module.run_command(
        SimpleNamespace(output=output), report_builder=lambda _args: _report()
    )

    assert result["execution_authority"] == "none"
    assert result["generator_identity"]["files"]
    assert output.is_file()


def test_command_rejects_authority_shaped_report(tmp_path: Path) -> None:
    """Any nested attempt to shape the report as live must fail before writing."""
    module = _module()
    output = tmp_path / "rejected.json"
    payload = {**_report(), "execution_authority": "live"}

    with pytest.raises(ValueError, match="report-only contract"):
        module.run_command(
            SimpleNamespace(output=output), report_builder=lambda _args: payload
        )

    assert not output.exists()


def test_krown_execution_translates_15_minute_hold_contract() -> None:
    """The reused friction evidence must retain a 24-hour hold at 15 minutes."""
    module = _module()
    execution = MuArchiveExecution(0.0001, 75.0, 20.0, 1.0, 2.0, 0.0, 80.0, 288)
    bars = pd.DataFrame(
        columns=["risk_high", "risk_low", "risk_entry_high", "risk_entry_low"]
    )

    translated = module._krown_execution(execution, bars)

    assert translated.maximum_hold_bars == 96
    assert translated.effective_taker_fee_rate == execution.effective_taker_fee_rate
    assert translated.nominal_latency_bps_per_side == 1.0
    assert translated.stress_latency_bps_per_side == 2.0
