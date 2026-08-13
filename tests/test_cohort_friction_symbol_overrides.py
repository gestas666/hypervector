"""Exact symbol overrides in report-only execution-friction parity."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_execution_opportunity_matrix import (
    provider_replay_settings,
)
from hypervector.research.cohort_friction_parity import build_friction_parity


_RANGE = "range_onset_bidirectional_v1"
_V51 = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)


def test_sol_range_parity_uses_exact_symbol_stop_override() -> None:
    """SOL must report its bound 80-bps contract, not the 60-bps default."""
    identity = {
        "assets": [{"symbol": "SOL"}],
        "providers": [
            {
                "strategy_id": _RANGE,
                "symbols": ["SOL"],
                "stop_bps_overrides": {"SOL": 80.0},
                "execution": {
                    "entry_liquidity": "taker_ioc",
                    "stop_policy": "fixed_bps",
                    "target_policy": "none",
                    "maximum_hold_seconds": 172_800,
                    "stop_bps": 60.0,
                },
            }
        ],
    }

    row = build_friction_parity(identity, [])["by_provider_symbol"][f"{_RANGE}|SOL"]

    assert row["runtime_contract"]["stop_bps"] == 80.0
    assert row["runtime_contract_source"] == "provider_execution_symbol_override"
    assert row["modeled_contract"]["stop_bps"] == 80.0
    assert row["modeled_contract"]["evidence_source"].endswith(
        "v51_growth_sizing_stress_20260813_v1.json"
    )
    assert row["parity_state"] == "runtime_shape_aligned"
    assert row["mismatches"] == []


def test_opportunity_matrix_uses_sol_symbol_stop_override() -> None:
    """Missed-opportunity loss estimates must also use the bound SOL stop."""
    config = load_multi_asset_live_config(_V51, mode="observe")

    settings = provider_replay_settings(config)

    assert settings[(_RANGE, "ETH")].stop_proxy_bps == 60.0
    assert settings[(_RANGE, "SOL")].stop_proxy_bps == 80.0
