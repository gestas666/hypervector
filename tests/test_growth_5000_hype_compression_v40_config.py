"""Growth-profile parity tests for the corrected v39 strategy roster."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_CURRENT = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_GROWTH = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_candidate_v40.toml"
)
_RETIRED = {
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
    "range_onset_bidirectional_v1",
}


def _load(path: Path) -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        path,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )


def test_v40_changes_sizing_without_changing_the_corrected_roster() -> None:
    """Growth preparation must not silently reintroduce retired routes or assets."""
    current = _load(_CURRENT)
    growth = _load(_GROWTH)

    assert growth.profile_id.endswith("v40")
    assert growth.maximum_positions == current.maximum_positions == 10
    assert growth.symbols == current.symbols
    assert growth.providers == current.providers
    assert "xyz:GOLD" not in growth.symbols
    assert _RETIRED.isdisjoint(provider.strategy_id for provider in growth.providers)


def test_v40_is_three_percent_margin_at_five_x_for_every_asset() -> None:
    """Each slot represents 3% margin and 15% notional of a $5,000 portfolio."""
    growth = _load(_GROWTH)

    for asset in growth.assets:
        assert asset.margin_fraction == pytest.approx(0.03)
        assert asset.leverage == pytest.approx(5.0)
        assert asset.max_notional_usd == pytest.approx(750.0)

    assert sum(asset.margin_fraction for asset in growth.assets) == pytest.approx(0.24)
    assert growth.maximum_positions * 0.03 == pytest.approx(0.30)


def test_v40_has_no_observe_only_provider_routes() -> None:
    """Every declared provider-symbol route must carry live execution authority."""
    growth = _load(_GROWTH)

    for provider in growth.providers:
        assert provider.execution_symbols == provider.symbols
