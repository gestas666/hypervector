"""Configuration validation for the retained HYPE alignment route."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

_SPCX_CONTAINMENT = Path("tests/fixtures/profiles/spcx_short_containment.toml")


def _alignment(config: MultiAssetLiveConfig) -> StrategyProviderConfig:
    return next(
        provider
        for provider in config.providers
        if provider.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
    )


def _replace_alignment(
    config: MultiAssetLiveConfig,
    provider: StrategyProviderConfig,
) -> MultiAssetLiveConfig:
    providers = tuple(
        provider if row.strategy_id == provider.strategy_id else row
        for row in config.providers
    )
    return replace(config, providers=providers)


def test_hype_alignment_exact_contract_is_valid() -> None:
    """The current HYPE alignment contract remains loadable unchanged."""
    config = load_multi_asset_live_config(_SPCX_CONTAINMENT, mode="observe")

    validate_multi_asset_live_config(config)


@pytest.mark.parametrize(
    "execution_changes",
    [
        {"stop_bps": 60.0},
        {"maximum_hold_seconds": 21_600},
        {
            "maximum_hold_policy": "fixed",
            "hard_maximum_hold_seconds": None,
            "maximum_hold_evidence_maximum_age_seconds": None,
        },
        {"hard_maximum_hold_seconds": 43_200},
        {"maximum_hold_evidence_maximum_age_seconds": 61},
    ],
)
def test_hype_alignment_accepts_its_own_exit_contract(
    execution_changes: dict[str, object],
) -> None:
    """Stop, hold, and freshness values are the profile's, not the provider ID's."""
    config = load_multi_asset_live_config(_SPCX_CONTAINMENT, mode="observe")
    provider = _alignment(config)
    reused = replace(
        provider,
        execution=replace(provider.execution, **execution_changes),
    )

    validate_multi_asset_live_config(_replace_alignment(config, reused))


@pytest.mark.parametrize(
    ("provider_changes", "execution_changes"),
    [
        ({"timeframe": "5m"}, {}),
        ({"position_policy": "flat_entry_only"}, {}),
        (
            {},
            {
                "stop_policy": "structural_clamped_bps",
                "stop_bps": None,
                "minimum_stop_bps": 20.0,
                "maximum_stop_bps": 80.0,
            },
        ),
    ],
)
def test_hype_alignment_rejects_what_its_signal_cannot_bind(
    provider_changes: dict[str, object],
    execution_changes: dict[str, object],
) -> None:
    """A mislabeled clock, a lost close, or an anchorless structural stop is refused."""
    config = load_multi_asset_live_config(_SPCX_CONTAINMENT, mode="observe")
    provider = _alignment(config)
    mutated = replace(
        provider,
        **provider_changes,
        execution=replace(provider.execution, **execution_changes),
    )

    with pytest.raises(MultiAssetLiveConfigError, match="alignment breakout"):
        validate_multi_asset_live_config(_replace_alignment(config, mutated))
