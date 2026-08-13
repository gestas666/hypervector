"""Contract tests for the focused inactive $5K v42 successor."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_CONFIG = Path(
    "configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml"
)
_EXPECTED_SIZING = {
    "BTC": (0.03133234273663189, 784.0),
    "HYPE": (0.030968520129647494, 775.0),
    "xyz:SP500": (0.03440089009678622, 861.0),
}
_EXPECTED_ROUTES = {
    ("hulk_expansion_bidirectional_tuned_v2", "BTC"),
    ("hype_breakout_compression_pullback_bidirectional_v1", "HYPE"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
}


def test_v42_contains_only_the_three_focused_bidirectional_routes() -> None:
    """Falsified v39/v41 routes cannot leak into the growth successor."""
    config = _load()

    assert config.profile_id.endswith("v42")
    assert config.symbols == tuple(_EXPECTED_SIZING)
    assert config.maximum_positions == 10
    assert config.executable_provider_symbols == frozenset(_EXPECTED_ROUTES)
    assert config.executable_provider_directions == frozenset(
        (provider, symbol, side)
        for provider, symbol in _EXPECTED_ROUTES
        for side in ("long", "short")
    )
    assert all(
        provider.execution_symbols == provider.symbols for provider in config.providers
    )


def test_v42_preserves_retained_v41_weights_without_redistribution() -> None:
    """Removed assets leave unused risk rather than enlarging surviving routes."""
    config = _load()

    for asset in config.assets:
        margin, cap = _EXPECTED_SIZING[asset.symbol]
        assert asset.margin_fraction == pytest.approx(margin)
        assert asset.max_notional_usd == pytest.approx(cap)
        assert asset.leverage == pytest.approx(5.0)
        assert 5_000.0 * margin * asset.leverage <= cap

    assert sum(asset.margin_fraction for asset in config.assets) == pytest.approx(
        0.0967017529620656
    )


def test_v42_preserves_provider_specific_exit_contracts() -> None:
    """The successor prunes entries without installing rejected exit changes."""
    providers = {provider.strategy_id: provider for provider in _load().providers}
    hype = providers["hype_breakout_compression_pullback_bidirectional_v1"].execution
    hulk = providers["hulk_expansion_bidirectional_tuned_v2"].execution
    hip3 = providers["hip3_breakout_pressure_sp500_spcx_bidirectional_v1"].execution

    assert hype.maximum_hold_policy == "extend_while_regime_supported"
    assert hype.maximum_hold_seconds == 28_800
    assert hype.hard_maximum_hold_seconds == 86_400
    assert hype.target_policy == "none"
    assert hulk.target_policy == "reward_risk"
    assert hulk.target_r_multiple == pytest.approx(3.0)
    assert hip3.maximum_hold_seconds == 86_400
    assert hip3.stop_bps == pytest.approx(80.0)


def _load() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        _CONFIG,
        mode="observe",
        enabled=False,
        accepts_live_risk=False,
    )
