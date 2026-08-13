"""Growth-profile tests for exact-repriced risk-normalized allocation."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_route_cycle import provider_bounded_fallback_hold_ms

_V40 = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_candidate_v40.toml"
)
_V41 = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_EXPECTED = {
    "BTC": (0.03133234273663189, 784.0),
    "ETH": (0.03212856592356959, 804.0),
    "SOL": (0.031042024396104317, 777.0),
    "HYPE": (0.030968520129647494, 775.0),
    "xyz:SP500": (0.03440089009678622, 861.0),
    "xyz:SPCX": (0.030068036523466714, 752.0),
    "xyz:SNDK": (0.024190292225340568, 605.0),
    "xyz:BRENTOIL": (0.02586932796845322, 647.0),
}


def test_v41_changes_only_asset_sizing_from_v40() -> None:
    """Risk normalization preserves the exact strategy and asset roster."""
    v40 = _load(_V40)
    v41 = _load(_V41)

    assert v41.profile_id.endswith("v41")
    assert v41.symbols == v40.symbols
    assert v41.providers == v40.providers
    assert v41.maximum_positions == v40.maximum_positions == 10
    assert all(asset.leverage == pytest.approx(5.0) for asset in v41.assets)


def test_v41_preserves_24_percent_margin_with_exact_repriced_weights() -> None:
    """Every configured percentage and nonbinding ceiling matches the audit."""
    v41 = _load(_V41)

    assert set(v41.symbols) == set(_EXPECTED)
    for asset in v41.assets:
        margin, cap = _EXPECTED[asset.symbol]
        assert asset.margin_fraction == pytest.approx(margin)
        assert asset.max_notional_usd == pytest.approx(cap)
        planned = 5_000.0 * asset.margin_fraction * asset.leverage
        assert planned <= asset.max_notional_usd

    assert sum(asset.margin_fraction for asset in v41.assets) == pytest.approx(0.24)


def test_v41_legacy_recovery_fallback_matches_24_hour_stress_horizon() -> None:
    """Planless recovery cannot outlive every authorized provider contract."""
    v41 = _load(_V41)
    configured = {
        asset.symbol: asset.maximum_hold_seconds * 1_000 for asset in v41.assets
    }
    contracts = {provider.strategy_id: provider.execution for provider in v41.providers}

    bounded = provider_bounded_fallback_hold_ms(
        configured,
        contracts,
        v41.executable_provider_symbols,
    )
    provider_terminals = {
        provider.strategy_id: (
            provider.execution.hard_maximum_hold_seconds
            if provider.execution.maximum_hold_policy == "extend_while_regime_supported"
            else provider.execution.maximum_hold_seconds
        )
        for provider in v41.providers
    }

    assert configured["BTC"] == 172_800_000
    assert {symbol for _, symbol in v41.executable_provider_symbols} == set(v41.symbols)
    assert all(
        terminal is not None and terminal <= 86_400
        for terminal in provider_terminals.values()
    )
    assert set(bounded) == set(v41.symbols)
    assert all(value <= 86_400_000 for value in bounded.values())


def test_recovery_bound_preserves_an_explicit_48_hour_provider_contract() -> None:
    """Provider-derived recovery does not introduce an implicit 24-hour gate."""
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=172_800,
    )

    bounded = provider_bounded_fallback_hold_ms(
        {"BTC": 172_800_000},
        {"provider": contract},
        frozenset({("provider", "BTC")}),
    )

    assert bounded == {"BTC": 172_800_000}


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
