"""Restart-only cohort profile staging tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_operator_commands import (
    CohortAssetStage,
    CohortProfileSettings,
    CohortProviderStage,
)
from hypervector.live.cohort_profile_stage import stage_cohort_profile
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


def _settings() -> CohortProfileSettings:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    return CohortProfileSettings(
        maximum_positions=len(config.assets),
        poll_seconds=10.0,
        assets=tuple(
            CohortAssetStage(
                asset.symbol,
                4.0,
                0.02,
                75.0 if asset.symbol == "SOL" else 20.0,
                70.0,
                21_600,
            )
            for asset in config.assets
        ),
        providers=tuple(
            CohortProviderStage(provider.strategy_id, provider.execution_symbols)
            for provider in config.providers
        ),
    )


def test_stage_writes_a_loadable_disarmed_profile_without_mutating_source(
    tmp_path: Path,
) -> None:
    """A valid full patch becomes a separate restart-only TOML profile."""
    source = Path("tests/fixtures/profiles/multi_asset_bidirectional_canary.toml")
    before = source.read_bytes()
    config = load_multi_asset_live_config(source, mode="observe")
    output = tmp_path / "staged.toml"

    reason = stage_cohort_profile(
        config=config, settings=_settings(), output_path=output
    )

    staged = load_multi_asset_live_config(output, mode="observe")
    assert staged.maximum_positions == len(staged.assets) == 4
    assert staged.poll_seconds == 10.0
    assert staged.assets[0].leverage == 4.0
    assert staged.assets[0].margin_fraction == 0.02
    assert staged.providers[0].execution == config.providers[0].execution
    assert staged.providers[2].execution == config.providers[2].execution
    assert "apply only by disarmed restart" in reason
    assert source.read_bytes() == before


def test_stage_rejects_venue_leverage_and_incomplete_provider_scope(
    tmp_path: Path,
) -> None:
    """The generated profile uses the same venue and provider validation."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    settings = _settings()
    unsafe_asset = replace(settings.assets[-1], leverage=50.0)
    unsafe = replace(settings, assets=(*settings.assets[:-1], unsafe_asset))
    with pytest.raises(ValueError, match="leverage exceeds"):
        stage_cohort_profile(
            config=config,
            settings=unsafe,
            output_path=tmp_path / "unsafe.toml",
        )

    incomplete = replace(settings, providers=settings.providers[:-1])
    with pytest.raises(ValueError, match="cover every configured provider"):
        stage_cohort_profile(
            config=config,
            settings=incomplete,
            output_path=tmp_path / "incomplete.toml",
        )


def test_stage_preserves_provider_direction_overrides(tmp_path: Path) -> None:
    """Restart-only editing cannot widen an existing direction restriction."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    providers = tuple(
        replace(
            provider,
            execution_side_overrides=(("ETH", frozenset({"long"})),),
        )
        if provider.strategy_id == "range_onset_bidirectional_v1"
        else provider
        for provider in config.providers
    )
    restricted = replace(config, providers=providers)
    output = tmp_path / "restricted-staged.toml"

    stage_cohort_profile(
        config=restricted,
        settings=_settings(),
        output_path=output,
    )

    staged = load_multi_asset_live_config(output, mode="observe")
    provider = next(
        row
        for row in staged.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )
    assert provider.execution_side_overrides == (("ETH", frozenset({"long"})),)
    assert provider.entry_context_overrides == (("ETH", "dual_mtf_not_opposed"),)


def test_stage_preserves_provider_symbol_sizing_overrides(tmp_path: Path) -> None:
    """Restart-only editing cannot silently discard provider allocation."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    sizing = CohortEntrySizing(0.04, 15.0)
    providers = tuple(
        replace(provider, sizing_overrides=(("SOL", sizing),))
        if provider.strategy_id == "range_onset_bidirectional_v1"
        else provider
        for provider in config.providers
    )
    output = tmp_path / "sizing-staged.toml"

    stage_cohort_profile(
        config=replace(config, providers=providers),
        settings=_settings(),
        output_path=output,
    )

    staged = load_multi_asset_live_config(output, mode="observe")
    provider = next(
        row
        for row in staged.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )
    assert provider.entry_sizing("SOL") == sizing


def test_stage_preserves_provider_directional_sizing_overrides(tmp_path: Path) -> None:
    """Restart-only editing cannot discard an explicit route-side allocation."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )
    long_policy = CohortEntrySizing(0.08, 60.0)
    short_policy = CohortEntrySizing(0.02, 15.0)
    providers = tuple(
        replace(
            provider,
            directional_sizing_overrides=(
                ("SOL", "long", long_policy),
                ("SOL", "short", short_policy),
            ),
        )
        if provider.strategy_id == "range_onset_bidirectional_v1"
        else provider
        for provider in config.providers
    )
    output = tmp_path / "directional-sizing-staged.toml"

    stage_cohort_profile(
        config=replace(config, providers=providers),
        settings=_settings(),
        output_path=output,
    )

    staged = load_multi_asset_live_config(output, mode="observe")
    provider = next(
        row
        for row in staged.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )
    assert provider.entry_sizing("SOL", "long") == long_policy
    assert provider.entry_sizing("SOL", "short") == short_policy
