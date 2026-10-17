"""Exact configuration validation for the retained HYPE alignment route."""

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

_V57 = Path("tests/fixtures/profiles/multi_asset_growth_first_5000_spcx_short_containment_v57.toml")


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


def test_v57_hype_alignment_exact_contract_is_valid() -> None:
    """The current v57 HYPE alignment contract remains loadable unchanged."""
    config = load_multi_asset_live_config(_V57, mode="observe")

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
def test_v57_hype_alignment_rejects_mutated_exit_contract(
    execution_changes: dict[str, object],
) -> None:
    """Stop, hold, and freshness drift cannot retain the frozen provider ID."""
    config = load_multi_asset_live_config(_V57, mode="observe")
    provider = _alignment(config)
    mutated = replace(
        provider,
        execution=replace(provider.execution, **execution_changes),
    )

    with pytest.raises(MultiAssetLiveConfigError, match="alignment breakout"):
        validate_multi_asset_live_config(_replace_alignment(config, mutated))
