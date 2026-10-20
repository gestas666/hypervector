"""Tests for exact cohort configuration telemetry projections."""

from pathlib import Path

from hypervector.live.multi_asset_cohort_payloads import provider_config_payload
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


_REPAIRED_A = Path("tests/fixtures/profiles/repaired_a.toml")


def test_provider_payload_preserves_directional_authority() -> None:
    """Telemetry must not relabel one-sided providers as bidirectional."""
    config = load_multi_asset_live_config(_REPAIRED_A, mode="observe")
    sides = {
        provider.strategy_id: provider_config_payload(provider)["sides"]
        for provider in config.providers
    }

    assert sides["hulk_expansion_short_robust_v3"] == ["short"]
    assert sides["liquidity_sweep_long_1h_stop60_target60_v2"] == ["long"]
    assert sides["range_onset_bidirectional_v1"] == ["long", "short"]
