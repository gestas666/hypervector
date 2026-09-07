"""Source-bound cost projections for the three V89 hourly additions."""

from pathlib import Path

import pytest

from hypervector.live.multi_asset_cohort_payloads import (
    asset_config_payload,
    provider_config_payload,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_friction_contracts import modeled_contract
from hypervector.research.cohort_friction_parity import build_friction_parity

_PROFILE = Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml")
_ROUTES = (
    ("hourly_band20_reentry_atr20_bidirectional_v1", "xyz:SPCX"),
    ("hourly_donchian_20_10_atr20_bidirectional_v1", "xyz:SNDK"),
    ("hourly_donchian_8_4_atr20_bidirectional_v1", "xyz:BRENTOIL"),
)


def _identity() -> dict[str, object]:
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    return {
        "assets": [asset_config_payload(asset) for asset in config.assets],
        "providers": [
            provider_config_payload(provider) for provider in config.providers
        ],
    }


def test_current_roster_has_seven_supported_cost_comparisons() -> None:
    """A supported runtime route must not lose its existing research comparison."""
    report = build_friction_parity(_identity(), [])
    assert report["summary"] == {
        "provider_symbols": 7,
        "runtime_shape_aligned": 7,
        "contract_mismatch": 0,
        "unsupported_contract": 0,
        "runtime_contract_missing": 0,
        "provider_symbols_with_entry_fills": 0,
    }
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_pause"] is False


@pytest.mark.parametrize("strategy,symbol", _ROUTES)
def test_hourly_route_uses_frozen_nominal_cost_and_exit_mechanics(
    strategy: str, symbol: str
) -> None:
    """Modeled nominal friction cannot masquerade as measured live fills."""
    row = build_friction_parity(_identity(), [])["by_provider_symbol"][
        f"{strategy}|{symbol}"
    ]
    modeled = row["modeled_contract"]
    assert modeled is not None
    assert modeled["entry_liquidity"] == "taker"
    assert modeled["entry_fee_bps"] == pytest.approx(0.9)
    assert modeled["entry_slippage_bps"] == pytest.approx(2.5)
    assert modeled["stop_policy"] == "structural_clamped_bps"
    assert modeled["stop_bps"] is None
    assert modeled["minimum_stop_bps"] == 20.0
    assert modeled["maximum_stop_bps"] == 250.0
    assert modeled["maximum_hold_policy"] == "fixed"
    assert modeled["maximum_hold_seconds"] == 86_400
    assert modeled["target_policy"] == "none"
    assert modeled["target_liquidity"] is None
    assert modeled["evidence_source"].endswith(
        "v89_hourly_nominal_friction_contracts_20260907_v1.json"
    )
    assert row["observed_entry"]["status"] == "not_observed"
    assert row["observed_entry"]["fee_mean_minus_modeled_bps"] is None
    assert row["strategy_edge_identifiable"] is False
    assert row["runtime_contract"]["provider_recipe_exit_policy"] == "honor"


@pytest.mark.parametrize("strategy,symbol", _ROUTES)
def test_hourly_cost_mapping_does_not_fall_back_to_unresearched_assets(
    strategy: str, symbol: str
) -> None:
    """Sharing a recipe identity cannot imply research on a different asset."""
    assert modeled_contract(strategy, "xyz:GOLD") is None
    assert modeled_contract(strategy, None) is None
    other = next(asset for _, asset in _ROUTES if asset != symbol)
    assert modeled_contract(strategy, other) is None


def test_actual_costs_are_compared_against_the_frozen_model() -> None:
    """Observed entry fees and slippage retain their own values and signed deltas."""
    strategy, symbol = _ROUTES[0]
    fill = {
        "operation": "entry",
        "strategy_id": strategy,
        "symbol": symbol,
        "price": 100.0,
        "size": 5.0,
        "fee_usd": 0.04,
        "slippage_bps": 2.0,
        "acknowledgement_latency_ms": 200,
    }
    row = build_friction_parity(_identity(), [fill])["by_provider_symbol"][
        f"{strategy}|{symbol}"
    ]
    observed = row["observed_entry"]
    assert observed["status"] == "observed"
    assert observed["fills"] == 1
    assert observed["fee_rate_bps"]["mean"] == pytest.approx(0.8)
    assert observed["fee_mean_minus_modeled_bps"] == pytest.approx(-0.1)
    assert observed["slippage_mean_minus_modeled_bps"] == pytest.approx(-0.5)


def test_model_comparison_still_exposes_a_changed_runtime_stop() -> None:
    """Filling missing evidence must not suppress a real contract mismatch."""
    identity = _identity()
    provider = identity["providers"][-1]
    provider["execution"]["maximum_stop_bps"] = 300.0
    row = build_friction_parity(identity, [])["by_provider_symbol"][
        f"{_ROUTES[-1][0]}|{_ROUTES[-1][1]}"
    ]
    assert row["parity_state"] == "contract_mismatch"
    assert "stop_bounds" in row["mismatches"]
