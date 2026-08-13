"""Growth-oriented sizing contract for the BTC-specialist successor."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V44 = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)
_V45 = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)


def test_v45_changes_only_hype_and_sp500_base_sizing() -> None:
    """The growth candidate preserves every v44 strategy and exit contract."""
    v44 = load_multi_asset_live_config(_V44, mode="observe")
    v45 = load_multi_asset_live_config(_V45, mode="observe")

    assert v45.profile_id.endswith("growth_sizing_candidate_v45")
    assert v45.providers == v44.providers
    assert v45.maximum_positions == v44.maximum_positions == 10
    assert v45.symbols == v44.symbols == ("BTC", "HYPE", "xyz:SP500")

    old_assets = {asset.symbol: asset for asset in v44.assets}
    assets = {asset.symbol: asset for asset in v45.assets}
    assert (
        replace(assets["BTC"], parent_profile_id=old_assets["BTC"].parent_profile_id)
        == old_assets["BTC"]
    )
    for symbol in ("HYPE", "xyz:SP500"):
        assert assets[symbol].margin_fraction == pytest.approx(0.07)
        assert assets[symbol].max_notional_usd == pytest.approx(1_750.0)
        assert assets[symbol].leverage == pytest.approx(5.0)


def test_v45_scales_one_percent_policy_across_canary_and_growth_equity() -> None:
    """The same fractions produce $175 then $1,750 route notionals."""
    config = load_multi_asset_live_config(_V45, mode="observe")
    assets = {asset.symbol: asset for asset in config.assets}

    for symbol in ("HYPE", "xyz:SP500"):
        asset = assets[symbol]
        assert 500.0 * asset.margin_fraction * asset.leverage == pytest.approx(175.0)
        assert 5_000.0 * asset.margin_fraction * asset.leverage == pytest.approx(
            1_750.0
        )
    assert sum(asset.margin_fraction for asset in config.assets) == pytest.approx(
        0.3066666666666667
    )
    assert sum(
        asset.margin_fraction * asset.leverage for asset in config.assets
    ) == pytest.approx(1.5333333333333334)


def test_v45_keeps_leverage_fixed_until_strength_is_forward_calibrated() -> None:
    """Unvalidated readiness or regime scores cannot enlarge live exposure."""
    config = load_multi_asset_live_config(_V45, mode="observe")

    assert {asset.leverage for asset in config.assets} == {5.0}
    assert all(
        "sizing" not in provider.strategy_id and provider.sizing_overrides == ()
        for provider in config.providers
        if provider.strategy_id.startswith(("hype_", "hip3_"))
    )
