"""Authority tests for the all-asset HYPE-breakout transfer observer."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_evidence_payloads,
)

_PROFILE = Path("tests/fixtures/profiles/all_asset_hype_breakout_transfer_v1.toml")
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def test_all_asset_transfer_profile_is_execution_incapable() -> None:
    """Every supported coin is observed without inheriting order authority."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    assert config.profile_id == "all_asset_hype_breakout_transfer_observer_v1"
    assert config.symbols == _SYMBOLS
    assert config.maximum_positions == 4
    assert config.executable_provider_symbols == frozenset()
    assert config.poll_seconds == 60.0
    assert len(config.providers) == 1
    provider = config.providers[0]
    assert provider.strategy_id == "hype_breakout_onset_bidirectional_v1"
    assert provider.symbols == _SYMBOLS
    assert provider.sides == frozenset({"long", "short"})
    assert provider.execution_symbols == ()


def test_all_asset_transfer_profile_refuses_live_authority() -> None:
    """Explicit live flags still cannot arm an empty execution scope."""
    with pytest.raises(
        MultiAssetLiveConfigError,
        match="at least one explicit provider execution symbol",
    ):
        load_multi_asset_live_config(
            _PROFILE,
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        )


def test_default_factory_builds_all_asset_breakout_collectors() -> None:
    """The production factory must accept the four-symbol observer scope."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert isinstance(poller, ConfiguredMultiAssetIntentPoller)


def test_all_asset_transfer_profile_reports_reviewed_mapping_evidence() -> None:
    """The observer must not label already-reviewed transfers as unreviewed."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    evidence = {
        row["symbol"]: row for row in strategy_evidence_payloads(config.providers)
    }

    assert evidence["BTC"]["research_state"] == "unstable_recent_short_observer"
    assert evidence["BTC"]["confidence"] == "low"
    assert "development" in evidence["BTC"]["summary"]
    assert "final-60-day" in evidence["BTC"]["summary"]
    assert evidence["ETH"]["research_state"] == "historical_transfer_rejected"
    assert evidence["SOL"]["research_state"] == "historical_transfer_rejected"
    assert evidence["ETH"]["confidence"] == "medium"
    assert evidence["SOL"]["confidence"] == "medium"
    assert all(
        row["evidence_source"]
        == "docs/reviews/2026-08-05-hype-breakout-cross-asset-transfer.md"
        for symbol, row in evidence.items()
        if symbol != "HYPE"
    )
    assert all(row["execution_effect"] == "report_only" for row in evidence.values())
    assert config.executable_provider_symbols == frozenset()
