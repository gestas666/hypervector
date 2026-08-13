"""Exact-delta contract for the inactive route-hardening v34 candidate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V33 = Path("configs/multi_asset_bidirectional_spcx_swing_retired_candidate_v33.toml")
_V34 = Path("configs/multi_asset_bidirectional_route_hardening_canary_v34.toml")
_RANGE = "range_onset_bidirectional_v1"
_INDEX_SWING = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_COMMODITY_SWING = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1"


def test_v34_changes_only_explicit_route_authority_and_eth_context() -> None:
    """The successor may not silently change risk, exits, or other providers."""
    source = _raw(_V33)
    candidate = _raw(_V34)

    source["profile"] = candidate["profile"]
    source_range = _provider(source, _RANGE)
    source_range["execution_symbols"] = ["ETH", "SOL"]
    source_range["entry_context_overrides"] = {
        "ETH": "dual_mtf_not_opposed",
    }
    candidate_index_swing = _provider(candidate, _INDEX_SWING)
    assert candidate_index_swing["execution_symbols"] == []
    _provider(source, _INDEX_SWING)["execution_symbols"] = []

    assert source == candidate


def test_v34_preserves_nine_assets_both_sides_and_observation() -> None:
    """Retired routes remain measurable while all asset slots stay available."""
    config = load_multi_asset_live_config(_V34, mode="observe")
    observed = _observed(config)

    assert config.maximum_positions == len(config.assets) == 9
    assert len(observed) == 24
    assert len(config.executable_provider_symbols) == 17
    assert observed - config.executable_provider_symbols == {
        (_RANGE, "BTC"),
        (_RANGE, "HYPE"),
        (_INDEX_SWING, "xyz:SP500"),
        (_INDEX_SWING, "xyz:SPCX"),
        (_COMMODITY_SWING, "xyz:SNDK"),
        (_COMMODITY_SWING, "xyz:GOLD"),
        (_COMMODITY_SWING, "xyz:BRENTOIL"),
    }
    for provider in config.providers:
        assert provider.sides == frozenset({"long", "short"})


def test_v34_preserves_risk_and_applies_only_measured_range_context() -> None:
    """Validate the exact live-facing context and risk contracts."""
    config = load_multi_asset_live_config(_V34, mode="observe")
    providers = {provider.strategy_id: provider for provider in config.providers}
    range_provider = providers[_RANGE]

    assert range_provider.execution_symbols == ("ETH", "SOL")
    assert range_provider.entry_context_overrides == (("ETH", "dual_mtf_not_opposed"),)
    assert range_provider.execution.stop_bps == 60.0
    assert range_provider.execution.maximum_hold_seconds == 172_800
    assert providers[_INDEX_SWING].execution_symbols == ()
    assert providers[_COMMODITY_SWING].execution_symbols == ()
    assert all(asset.leverage == 5.0 for asset in config.assets)


def test_v34_loader_does_not_mutate_v33_profile() -> None:
    """Loading the successor must not mutate the preserved v33 candidate."""
    source = load_multi_asset_live_config(_V33, mode="observe")
    before = deepcopy(source)

    load_multi_asset_live_config(_V34, mode="observe")

    assert source == before


def _raw(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _provider(config: dict[str, object], strategy_id: str) -> dict[str, object]:
    providers = config["providers"]
    assert isinstance(providers, list)
    matches = [row for row in providers if row["strategy_id"] == strategy_id]
    assert len(matches) == 1
    return matches[0]


def _observed(config: MultiAssetLiveConfig) -> set[tuple[str, str]]:
    return {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
