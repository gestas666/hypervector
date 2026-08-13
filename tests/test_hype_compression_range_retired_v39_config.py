"""Successor-profile tests for HYPE compression and Range Onset retirement."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.hype_breakout_compression_provider import (
    HYPE_COMPRESSION_BREAKOUT_STRATEGY,
    HypeCompressionBreakoutCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_CONFIG = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_CANONICAL = "hype_breakout_onset_bidirectional_v1"
_RANGE = "range_onset_bidirectional_v1"
_FINGERPRINT = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"


def test_v39_replaces_only_hype_immediate_breakout_and_retires_range() -> None:
    """The successor preserves eight assets while changing two explicit routes."""
    config = load_multi_asset_live_config(
        _CONFIG,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    providers = {provider.strategy_id: provider for provider in config.providers}

    assert config.profile_id.endswith("v39")
    assert config.maximum_positions == 10
    assert len(config.assets) == 8
    assert len(config.providers) == 7
    assert sum(len(provider.symbols) for provider in config.providers) == 14
    assert (
        sum(
            len(provider.execution_symbols) * len(provider.sides)
            for provider in config.providers
        )
        == 28
    )
    assert "xyz:GOLD" not in config.symbols
    assert _RANGE not in providers
    assert providers[_CANONICAL].symbols == ("BTC", "ETH", "SOL")
    assert providers[_CANONICAL].execution_symbols == ("BTC", "ETH", "SOL")
    filtered = providers[HYPE_COMPRESSION_BREAKOUT_STRATEGY]
    assert filtered.symbols == ("HYPE",)
    assert filtered.execution_symbols == ("HYPE",)
    assert filtered.execution.maximum_hold_policy == "extend_while_regime_supported"
    assert filtered.execution.hard_maximum_hold_seconds == 86_400


def test_disabled_profit_lock_preserves_the_running_v39_identity() -> None:
    """An additive disabled policy cannot alias the active profile fingerprint."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")

    assert config.profile_fingerprint == _FINGERPRINT
    assert all(
        provider.execution.profit_lock_policy == "none" for provider in config.providers
    )


def test_v39_builds_the_hype_filter_with_live_authority_telemetry() -> None:
    """The default registry resolves the new route to its exact collector."""
    config = load_multi_asset_live_config(
        _CONFIG,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_COMPRESSION_BREAKOUT_STRATEGY
    )

    collector = build_default_collector(provider, config, Path("../backtest-lab"))

    assert isinstance(collector, HypeCompressionBreakoutCollector)
