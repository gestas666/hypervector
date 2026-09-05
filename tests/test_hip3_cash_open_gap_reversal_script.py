"""Contract tests for the HIP-3 cash-open gap-reversal study."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v53-sp500-spcx-cash-open-gap-reversal-preregistration-v1.json"
)
_SCRIPT = Path("scripts/hip3_cash_open_gap_reversal_development.py")


def _module() -> object:
    """Load the report-only command with its script-local dependencies."""
    assert _SCRIPT.is_file(), "cash-open development script is missing"
    spec = spec_from_file_location("hip3_cash_open_gap_reversal_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent.resolve()))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _report() -> dict[str, object]:
    """Return the minimum accepted report-only payload."""
    return {
        "schema_version": "hip3_cash_open_gap_reversal_development_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
        "out_of_sample_economics": "WITHHELD_NOT_EVALUATED",
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def test_preregistration_freezes_distinct_report_only_hypothesis() -> None:
    """Require the economic and authority contract before any replay exists."""
    payload = json.loads(_PREREGISTRATION.read_text())
    contract = payload["frozen_contract"]
    assert payload["hypothesis_id"] == "V53_SP500_SPCX_CASH_OPEN_GAP_REVERSAL_V1"
    assert payload["state"] == "preregistered_development_only"
    assert payload["execution_authority"] == "none"
    assert payload["runtime_strategy_changed"] is False
    assert payload["live_configuration_changed"] is False
    assert contract["symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert contract["directions"] == ["long", "short"]
    assert contract["gap_threshold_bps"] == 20.0
    assert contract["stop_bps"] == 80.0
    assert contract["target"] == "prior_eligible_cash_session_close"
    assert contract["maximum_hold_bars"] == 25
    assert contract["validation_accessed"] is False
    assert contract["holdout_accessed"] is False


def test_command_publishes_only_zero_authority_evidence(tmp_path: Path) -> None:
    """Write an immutable diagnostic without constructing live authority."""
    module = _module()
    output = tmp_path / "cash-open.json"
    result = module.run_command(
        SimpleNamespace(output=output), report_builder=lambda _args: _report()
    )
    assert result["execution_authority"] == "none"
    assert result["generator_identity"]["files"]
    assert output.is_file()


def test_command_rejects_authority_shaped_report(tmp_path: Path) -> None:
    """Fail before publication when a payload claims live authority."""
    module = _module()
    output = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="report-only contract"):
        module.run_command(
            SimpleNamespace(output=output),
            report_builder=lambda _args: {**_report(), "execution_authority": "live"},
        )
    assert not output.exists()


def test_cost_contract_builds_fixed_gap_reversal_execution() -> None:
    """Preserve costs while refusing PnL-selected gap or exit parameters."""
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
            }
        },
    }
    execution, signal = module._execution_contract("xyz:SPCX", 20.0, liquidity, cost)
    assert execution.stress_visible_tail_bps_per_side == 7.0
    assert execution.fixed_stop_bps == 80.0
    assert execution.maximum_hold_bars == 25
    assert signal.gap_threshold_bps == 20.0
    assert signal.stop_bps == 80.0


def test_cost_contract_uses_the_preregistered_liquidity_notional() -> None:
    """Select the exact frozen MU depth rung instead of assuming five thousand."""
    module = _module()
    liquidity = {
        "profile": {
            "symbol": "xyz:MU",
            "notionals": [
                {
                    "notional_usd": 2000.0,
                    "both_complete_rate": 1.0,
                    "round_trip_visible_cost_bps": {"p90": 13.0, "p99": 47.0},
                    "round_trip_taker_total_cost_bps": {"p99": 48.728},
                }
            ],
        }
    }
    cost = {
        "portfolio_contract": {"notional_usd_per_position": 2000.0},
        "fee_evidence": {"effective_taker_rate": 0.0000864},
        "stress_contract": {
            "nominal_latency_bps_per_side": 1.0,
            "stress_latency_bps_per_side": 2.0,
        },
        "symbols": {
            "xyz:MU": {
                "p99_round_trip_visible_cost_bps": 47.0,
                "p99_round_trip_taker_total_cost_bps": 48.728,
            }
        },
    }

    execution, _signal = module._execution_contract("xyz:MU", 10.0, liquidity, cost)

    assert execution.notional_usd == 2000.0
    assert execution.stress_visible_tail_bps_per_side == 17.0
