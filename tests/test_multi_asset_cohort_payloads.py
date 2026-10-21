"""Tests for exact cohort configuration telemetry projections."""

from pathlib import Path

from hypervector.live.multi_asset_cohort_payloads import provider_config_payload
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


_MIXED_SIDES = Path("tests/fixtures/profiles/four_asset_mixed_sides.toml")


def test_provider_payload_preserves_directional_authority() -> None:
    """Telemetry must not relabel one-sided providers as bidirectional."""
    config = load_multi_asset_live_config(_MIXED_SIDES, mode="observe")
    sides = {
        provider.strategy_id: provider_config_payload(provider)["sides"]
        for provider in config.providers
    }

    assert sides["test_short_trend_5m"] == ["short"]
    assert sides["test_long_target_1m"] == ["long"]
    assert sides["test_breakout_1m"] == ["long", "short"]
