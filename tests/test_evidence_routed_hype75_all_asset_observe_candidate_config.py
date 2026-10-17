"""Contract tests for the unified all-asset HYPE observer candidate."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_V9 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml"
)
_V10 = Path(
    "configs/"
    "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml"
)
_V11 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_ETH_TRANSFER = "eth_breakout_precompression_pullback_bidirectional_v1"


def test_v10_expands_observation_without_expanding_order_authority() -> None:
    """The new profile adds observers while retaining two executable mappings."""
    prior = load_multi_asset_live_config(_V9, mode="observe")
    candidate = load_multi_asset_live_config(_V10, mode="observe")
    prior_providers = {row.strategy_id: row for row in prior.providers}
    providers = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10"
    )
    assert candidate.symbols == prior.symbols == _SYMBOLS
    assert candidate.maximum_positions == prior.maximum_positions
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_HYPE, "HYPE"),
    }

    for strategy_id, provider in providers.items():
        if strategy_id == _HYPE:
            assert provider.symbols == _SYMBOLS
            assert provider.execution_symbols == ("HYPE",)
            assert replace(provider, symbols=("HYPE",)) == prior_providers[strategy_id]
        else:
            assert provider == prior_providers[strategy_id]
    assert set(providers) == set(prior_providers)


def test_v10_live_identity_keeps_exact_two_mapping_authority() -> None:
    """Explicit live flags cannot make observed transfer mappings executable."""
    config = load_multi_asset_live_config(
        _V10,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    assert config.mode == "live"
    assert config.enabled is True
    assert config.accepts_live_risk is True
    config.require_live_start(credentials_present=True)
    assert config.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_HYPE, "HYPE"),
    }


@pytest.mark.integration
def test_v10_builds_all_transfer_collectors_with_reviewed_evidence() -> None:
    """All four visible HYPE mappings have collectors and explicit provenance."""
    config = load_multi_asset_live_config(_V10, mode="observe")
    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )
    evidence = {
        row["symbol"]: row
        for row in strategy_evidence_payloads(config.providers)
        if row["strategy_id"] == _HYPE
    }

    assert isinstance(poller, ConfiguredMultiAssetIntentPoller)
    assert set(evidence) == set(_SYMBOLS)
    assert evidence["BTC"]["research_state"] == "unstable_recent_short_observer"
    assert evidence["ETH"]["research_state"] == "historical_transfer_rejected"
    assert evidence["SOL"]["research_state"] == "historical_transfer_rejected"
    assert evidence["HYPE"]["research_state"] == ("historical_deployed_shape_negative")
    assert all(row["execution_effect"] == "report_only" for row in evidence.values())


@pytest.mark.integration
def test_v11_adds_the_frozen_eth_transfer_as_observation_only() -> None:
    """The selected ETH contract is visible but cannot place an order."""
    prior = load_multi_asset_live_config(_V10, mode="observe")
    config = load_multi_asset_live_config(_V11, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _ETH_TRANSFER)
    evidence = next(
        row
        for row in strategy_evidence_payloads(config.providers)
        if row["strategy_id"] == _ETH_TRANSFER and row["symbol"] == "ETH"
    )

    assert provider.symbols == ("ETH",)
    assert config.profile_id == (
        "multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11"
    )
    assert config.executable_provider_symbols == prior.executable_provider_symbols
    assert config.assets == tuple(
        replace(asset, parent_profile_id=config.profile_id) for asset in prior.assets
    )
    assert provider.sides == frozenset({"long", "short"})
    assert provider.timeframe == "1m"
    assert provider.execution_symbols == ()
    assert provider.execution.stop_policy == "fixed_bps"
    assert provider.execution.stop_bps == 60.0
    assert provider.execution.target_policy == "none"
    assert provider.execution.maximum_hold_seconds == 43_200
    assert evidence["research_state"] == "prospective_requalification_open_long_only"
    assert evidence["confidence"] == "low"
    assert evidence["evidence_source"] == (
        "docs/research-journal/eth-breakout-precompression-pullback-v17.json"
    )
    assert evidence["execution_effect"] == "report_only"

    ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )


def test_v11_live_identity_keeps_eth_transfer_report_only() -> None:
    """Live authority remains exactly BTC Hulk plus canonical HYPE breakout."""
    config = load_multi_asset_live_config(
        _V11,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    config.require_live_start(credentials_present=True)
    assert config.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_HYPE, "HYPE"),
    }
