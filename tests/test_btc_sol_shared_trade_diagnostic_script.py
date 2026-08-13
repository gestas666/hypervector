"""Tests for the BTC/SOL shared completed-trade diagnostic."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "btc_sol_shared_trade_diagnostic.py"


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("BTC/SOL shared-trade diagnostic script is missing")
    spec = spec_from_file_location("btc_sol_shared_trade_diagnostic", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_contract_is_report_only_and_freezes_sol_capacity() -> None:
    """The diagnostic must have no authority and retain the proven SOL size."""
    contract = _module().experiment_contract()

    assert contract["execution_authority"] == "none"
    assert contract["initial_equity_usd"] == 15_000.0
    assert contract["sol_effective_exposure"] == 0.15
    assert contract["sol_capital_base_cap_usd"] == 15_000.0
    assert contract["sol_notional_cap_usd"] == 2_250.0
    assert contract["evidence_lane_caps_each_trade_at_source_equity"] is True


def test_btc_adapter_derives_source_equity_and_maker_entry_fee() -> None:
    """BTC outcomes must normalize from the frozen 35% source artifact."""
    module = _module()
    payload = {
        "experiment_contract": {
            "allocation_fraction": 0.35,
            "initial_equity": 15_000.0,
            "leverage": 30.0,
        },
        "event_replays": {
            "strict_tuned": {
                "trades": [
                    {
                        "entry_time_utc": "2026-01-01T00:00:00+00:00",
                        "exit_time_utc": "2026-01-01T01:00:00+00:00",
                        "margin": 5_250.0,
                        "notional": 157_500.0,
                        "fees": 47.0,
                        "net_pnl": 350.0,
                        "status": "target_completed",
                    }
                ]
            }
        },
    }

    outcome = module.btc_outcomes(payload)[0]

    assert outcome.source_equity_usd == pytest.approx(15_000.0)
    assert outcome.margin_fraction == pytest.approx(0.35)
    assert outcome.entry_fee_usd == pytest.approx(23.625)
    assert outcome.net_pnl_usd == pytest.approx(350.0)


def test_sol_adapter_selects_only_frozen_capacity_trial() -> None:
    """SOL evidence must retain the 60-bps, 0.15x completed trial."""
    module = _module()
    payload = {
        "symbol": "SOL",
        "execution_authority": "none",
        "continuous": {
            "trials": [
                {
                    "trial_id": "stop=60__exposure=0.15",
                    "event_replay": {
                        "status": "complete",
                        "trades": [
                            {
                                "entry_snapshot_time_ms": 1_000,
                                "exit_snapshot_time_ms": 2_000,
                                "equity_before_usd": 15_000.0,
                                "isolated_margin_usd": 450.0,
                                "entry_fee_usd": 1.0,
                                "net_pnl_usd": 10.0,
                                "exit_reason": "signal",
                            }
                        ],
                    },
                }
            ]
        },
    }

    outcome = module.sol_outcomes((payload,))[0]

    assert outcome.symbol == "SOL"
    assert outcome.margin_fraction == pytest.approx(0.03)
    assert outcome.source_equity_usd == pytest.approx(15_000.0)
    assert outcome.net_pnl_usd == pytest.approx(10.0)
