"""Fail-closed contracts for reused v58 SOL and HIP-3 routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError


_V58 = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_ROBUST = "hulk_expansion_short_robust_v3"
_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2"
_ETH = "eth_breakout_precompression_pullback_bidirectional_v1"
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_compression_alignment_bidirectional_v2"
_INDEX = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_SPCX = "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1"
_COMMODITY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"


def _replace_provider(
    config: MultiAssetLiveConfig,
    provider: StrategyProviderConfig,
) -> MultiAssetLiveConfig:
    providers = tuple(
        provider if row.strategy_id == provider.strategy_id else row
        for row in config.providers
    )
    return replace(config, providers=providers)


@pytest.mark.parametrize(
    ("strategy", "changes"),
    [
        (_HULK, {"timeframe": "15m"}),
        (_HULK, {"maximum_entry_delay_seconds": 30}),
        (_COMMODITY, {"timeframe": "5m"}),
        (_COMMODITY, {"maximum_entry_delay_seconds": 60}),
    ],
)
def test_v58_reused_provider_identity_rejects_timing_drift(
    strategy: str,
    changes: dict[str, object],
) -> None:
    """Frozen provider IDs cannot silently retain altered timing semantics."""
    config = load_multi_asset_live_config(_V58, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == strategy)
    mutated = replace(provider, **changes)

    with pytest.raises(MultiAssetLiveConfigError):
        validate_multi_asset_live_config(_replace_provider(config, mutated))


@pytest.mark.parametrize(
    ("strategy", "changes"),
    [
        (_HULK, {"target_r_multiple": 2.0}),
        (_HULK, {"maximum_hold_seconds": 43_200}),
        (_COMMODITY, {"stop_bps": 60.0}),
        (_COMMODITY, {"maximum_hold_seconds": 43_200}),
    ],
)
def test_v58_reused_provider_identity_rejects_exit_drift(
    strategy: str,
    changes: dict[str, object],
) -> None:
    """Stop, target, and terminal hold changes require a new strategy ID."""
    config = load_multi_asset_live_config(_V58, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == strategy)
    mutated = replace(provider, execution=replace(provider.execution, **changes))

    with pytest.raises(MultiAssetLiveConfigError):
        validate_multi_asset_live_config(_replace_provider(config, mutated))


@pytest.mark.parametrize(
    ("strategy", "changes"),
    [
        (_ROBUST, {"maximum_entry_delay_seconds": 61}),
        (_ROBUST, {"position_policy": "flat_entry_only"}),
        (_SWEEP, {"position_policy": "flat_entry_only"}),
        (_ETH, {"maximum_entry_delay_seconds": 61}),
        (_ETH, {"position_policy": "flat_entry_only"}),
    ],
)
def test_v58_known_provider_rejects_entry_semantic_drift(
    strategy: str,
    changes: dict[str, object],
) -> None:
    """Versioned providers freeze timing and opposite-position handling."""
    config = load_multi_asset_live_config(_V58, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == strategy)
    mutated = replace(provider, **changes)

    with pytest.raises(MultiAssetLiveConfigError):
        validate_multi_asset_live_config(_replace_provider(config, mutated))


@pytest.mark.parametrize(
    ("strategy", "changes"),
    [
        (
            _ROBUST,
            {
                "maximum_hold_policy": "extend_while_regime_supported",
                "hard_maximum_hold_seconds": 172_800,
                "maximum_hold_evidence_maximum_age_seconds": 60,
            },
        ),
        (_SWEEP, {"provider_recipe_exit_policy": "honor"}),
        (
            _ETH,
            {
                "profit_lock_policy": "completed_bar_trailing",
                "profit_lock_activation_bps": 100.0,
                "profit_lock_floor_bps": 40.0,
                "profit_lock_giveback_bps": 80.0,
            },
        ),
        (_HULK, {"provider_recipe_exit_policy": "honor"}),
        (_HYPE, {"safety_stop_overlay": True}),
        (_INDEX, {"safety_stop_overlay": True}),
        (_SPCX, {"safety_stop_overlay": True}),
        (
            _COMMODITY,
            {
                "profit_lock_policy": "completed_bar_trailing",
                "profit_lock_activation_bps": 100.0,
                "profit_lock_floor_bps": 40.0,
                "profit_lock_giveback_bps": 80.0,
            },
        ),
    ],
)
def test_v58_known_provider_rejects_exit_modifier_drift(
    strategy: str,
    changes: dict[str, object],
) -> None:
    """Unversioned hold, recipe, lock, and safety overlays fail closed."""
    config = load_multi_asset_live_config(_V58, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == strategy)
    mutated = replace(provider, execution=replace(provider.execution, **changes))

    with pytest.raises(MultiAssetLiveConfigError):
        validate_multi_asset_live_config(_replace_provider(config, mutated))


def test_execution_side_override_cannot_exceed_provider_signal_sides() -> None:
    """A short-only signal identity cannot be relabeled as long authority."""
    config = load_multi_asset_live_config(_V58, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _ROBUST)
    mutated = replace(
        provider,
        execution_side_overrides=(("BTC", frozenset({"long"})),),
    )

    with pytest.raises(MultiAssetLiveConfigError):
        validate_multi_asset_live_config(_replace_provider(config, mutated))
