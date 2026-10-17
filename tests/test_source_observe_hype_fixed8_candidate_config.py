"""Contract tests for the source-observe, fixed-eight-hour HYPE candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_BASE = Path(
    "tests/fixtures/profiles/multi_asset_bidirectional_range_retired_hype_fixed8_candidate.toml"
)
_CANDIDATE = Path(
    "tests/fixtures/profiles/multi_asset_bidirectional_source_observe_hype_fixed8_candidate.toml"
)
_SCALED = Path(
    "tests/fixtures/profiles/multi_asset_bidirectional_hype_core75_source_observe_fixed8_candidate.toml"
)
_ROUTED = Path(
    "tests/fixtures/profiles/multi_asset_bidirectional_evidence_routed_hype75_fixed8_candidate.toml"
)
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"


def test_candidate_changes_only_source_follow_execution_authority() -> None:
    """The candidate must retain source telemetry while removing order authority."""
    base = load_multi_asset_live_config(_BASE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    base_providers = {row.strategy_id: row for row in base.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}

    assert (
        candidate.profile_id
        == "multi_asset_bidirectional_source_observe_hype_fixed8_v5"
    )
    assert candidate.symbols == base.symbols
    assert candidate.maximum_positions == base.maximum_positions
    assert candidate_providers.keys() == base_providers.keys()
    assert candidate.executable_provider_directions == (
        base.executable_provider_directions
        - {(_SOURCE, "BTC", "long"), (_SOURCE, "BTC", "short")}
    )

    for asset, base_asset in zip(candidate.assets, base.assets, strict=True):
        assert replace(asset, parent_profile_id=base.profile_id) == base_asset
    for strategy_id, provider in candidate_providers.items():
        if strategy_id != _SOURCE:
            assert provider == base_providers[strategy_id]

    source = candidate_providers[_SOURCE]
    base_source = base_providers[_SOURCE]
    assert source.symbols == ("BTC",)
    assert source.sides == frozenset({"long", "short"})
    assert source.execution_symbols == ()
    assert source.source_profile == base_source.source_profile
    assert (
        replace(source, execution_symbols=base_source.execution_symbols) == base_source
    )


def test_hype_core75_candidate_scales_only_breakout_provider_exposure() -> None:
    """The aggressive variant must not scale unrelated HYPE providers."""
    base = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    scaled = load_multi_asset_live_config(_SCALED, mode="observe")
    base_assets = {row.symbol: row for row in base.assets}
    scaled_assets = {row.symbol: row for row in scaled.assets}
    base_providers = {row.strategy_id: row for row in base.providers}
    scaled_providers = {row.strategy_id: row for row in scaled.providers}

    assert (
        scaled.profile_id
        == "multi_asset_bidirectional_hype_core75_source_observe_fixed8_v6"
    )
    assert scaled.executable_provider_directions == base.executable_provider_directions
    assert scaled.maximum_positions == base.maximum_positions
    assert scaled_providers.keys() == base_providers.keys()

    for symbol, asset in scaled_assets.items():
        expected_cap = (
            75.0 if symbol == "HYPE" else base_assets[symbol].max_notional_usd
        )
        assert asset.max_notional_usd == expected_cap
        assert (
            replace(
                asset,
                parent_profile_id=base.profile_id,
                max_notional_usd=base_assets[symbol].max_notional_usd,
            )
            == base_assets[symbol]
        )

    for strategy_id, provider in scaled_providers.items():
        if strategy_id != _HULK:
            assert provider == base_providers[strategy_id]

    hulk_hype = scaled_providers[_HULK].entry_sizing("HYPE")
    assert hulk_hype is not None
    assert hulk_hype.margin_fraction == 0.03
    assert hulk_hype.max_notional_usd == 25.0
    assert (
        replace(
            scaled_providers[_HULK],
            sizing_overrides=base_providers[_HULK].sizing_overrides,
        )
        == base_providers[_HULK]
    )


def test_evidence_routed_candidate_limits_orders_without_losing_observation() -> None:
    """Only evidence-bearing mappings may place; all mappings remain evaluated."""
    base = load_multi_asset_live_config(_SCALED, mode="observe")
    routed = load_multi_asset_live_config(_ROUTED, mode="observe")
    base_providers = {row.strategy_id: row for row in base.providers}
    routed_providers = {row.strategy_id: row for row in routed.providers}

    assert routed.profile_id == "multi_asset_bidirectional_evidence_routed_hype75_v7"
    assert routed.symbols == base.symbols
    assert routed.maximum_positions == base.maximum_positions
    assert routed.executable_provider_directions == frozenset(
        {
            (_HULK, "BTC", "long"),
            (_HULK, "BTC", "short"),
            (_HYPE, "HYPE", "long"),
            (_HYPE, "HYPE", "short"),
        }
    )

    for asset, base_asset in zip(routed.assets, base.assets, strict=True):
        assert replace(asset, parent_profile_id=base.profile_id) == base_asset
    for strategy_id, provider in routed_providers.items():
        if strategy_id != _HULK:
            assert provider == base_providers[strategy_id]

    hulk = routed_providers[_HULK]
    assert hulk.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert hulk.sides == frozenset({"long", "short"})
    assert hulk.execution_symbols == ("BTC",)
    assert hulk.sizing_overrides == ()
    assert (
        replace(
            hulk,
            execution_symbols=base_providers[_HULK].execution_symbols,
            sizing_overrides=base_providers[_HULK].sizing_overrides,
        )
        == base_providers[_HULK]
    )

    assets = {asset.symbol: asset for asset in routed.assets}
    assert routed_providers[_HYPE].entry_sizing("HYPE") is None
    assert hulk.entry_sizing("BTC") is None
    assert assets["HYPE"].max_notional_usd == 75.0
    assert assets["BTC"].max_notional_usd == 25.0
