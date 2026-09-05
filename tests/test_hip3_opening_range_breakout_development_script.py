"""Report-only CLI boundary for the HIP-3 opening-range replay."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


_SCRIPT = Path("scripts/hip3_opening_range_breakout_development.py")


def _module() -> object:
    assert _SCRIPT.is_file(), "opening-range development script is missing"
    spec = spec_from_file_location("hip3_opening_range_development_script", _SCRIPT)
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
        "schema_version": "hip3_us_cash_opening_range_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def test_command_publishes_only_zero_authority_evidence(tmp_path: Path) -> None:
    """A development result is immutable and incapable of live mutation."""
    module = _module()
    output = tmp_path / "opening-range.json"

    result = module.run_command(
        SimpleNamespace(output=output), report_builder=lambda _args: _report()
    )

    assert result["execution_authority"] == "none"
    assert result["generator_identity"]["files"]
    assert output.is_file()


def test_command_rejects_authority_shaped_report(tmp_path: Path) -> None:
    """A live-shaped payload fails before publication."""
    module = _module()
    output = tmp_path / "rejected.json"

    with pytest.raises(ValueError, match="report-only contract"):
        module.run_command(
            SimpleNamespace(output=output),
            report_builder=lambda _args: {**_report(), "execution_authority": "live"},
        )

    assert not output.exists()


def test_frozen_cost_contract_builds_exact_symbol_execution() -> None:
    """Per-symbol fees, clearance, and visible tail cannot drift during replay."""
    module = _module()
    liquidity = {
        "profile": {
            "symbol": "xyz:SPCX",
            "notionals": [
                {
                    "notional_usd": 5000.0,
                    "both_complete_rate": 1.0,
                    "round_trip_visible_cost_bps": {"p90": 7.0, "p99": 21.0},
                    "round_trip_taker_total_cost_bps": {"p99": 22.728},
                }
            ],
            "fees": {"effective_taker_rate": 0.0000864},
        }
    }
    cost = {
        "portfolio_contract": {"notional_usd_per_position": 5000.0},
        "fee_evidence": {"effective_taker_rate": 0.0000864},
        "stress_contract": {
            "nominal_latency_bps_per_side": 1.0,
            "stress_latency_bps_per_side": 2.0,
        },
        "symbols": {
            "xyz:SPCX": {
                "p99_round_trip_visible_cost_bps": 21.0,
                "p99_round_trip_taker_total_cost_bps": 22.728,
                "frozen_breakout_clearance_bps": 53.456,
            }
        },
    }

    execution, signal = module._execution_contract("xyz:SPCX", 20.0, liquidity, cost)

    assert execution.stress_visible_tail_bps_per_side == 7.0
    assert execution.effective_taker_fee_rate == 0.0000864
    assert execution.notional_usd == 5000.0
    assert signal.clearance_bps == 53.456
