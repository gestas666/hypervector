"""Disabling execution preserves the policy needed for an exact later re-enable."""

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_profit_lock_override import CohortProfitLockOverride
from hypervector.live.cohort_profile_stage import stage_cohort_profile
from hypervector.live.cohort_route_cycle import authority_reason
from hypervector.live.multi_asset_live_config import (
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from test_cohort_profile_stage_roundtrip import unchanged_settings

NONCRYPTO_PROFILE = Path("tests/fixtures/profiles/noncrypto_live.toml")


@pytest.mark.parametrize("index", range(7))
def test_disable_and_reenable_preserves_exact_policy(index: int, tmp_path: Path) -> None:
    """The scope switch alone removes authority; inactive overrides survive the round trip."""
    original = load_multi_asset_live_config(NONCRYPTO_PROFILE, mode="observe")
    settings = unchanged_settings(original)
    providers = list(settings.providers)
    providers[index] = replace(providers[index], execution_symbols=())
    disabled_path = tmp_path / "disabled.toml"
    stage_cohort_profile(config=original, settings=replace(settings, providers=tuple(providers)),
                         output_path=disabled_path)
    disabled = load_multi_asset_live_config(disabled_path, mode="observe")
    expected = list(original.providers)
    expected[index] = replace(expected[index], execution_symbols=())
    assert disabled.providers == tuple(expected)
    provider = original.providers[index]
    for symbol in provider.symbols:
        for side in provider.sides:
            intent = StrategyIntent(provider.strategy_id, symbol, side, 0, 1.0, "test scope")
            assert authority_reason(intent, disabled.executable_provider_symbols,
                                    disabled.executable_provider_directions) == "provider_symbol_observe_only"
    enabled_path = tmp_path / "enabled.toml"
    stage_cohort_profile(config=disabled, settings=settings, output_path=enabled_path)
    enabled = load_multi_asset_live_config(enabled_path, mode="observe")
    assert enabled.providers == original.providers
    assert enabled.executable_provider_directions == original.executable_provider_directions
    assert original == load_multi_asset_live_config(NONCRYPTO_PROFILE, mode="observe")


def test_inactive_override_still_requires_an_observed_provider_symbol() -> None:
    """Preserved settings cannot name an asset the provider does not observe."""
    original = load_multi_asset_live_config(NONCRYPTO_PROFILE, mode="observe")
    invalid = replace(original.providers[0], execution_symbols=(),
                      execution_side_overrides=(("ETH", frozenset({"long"})),))
    with pytest.raises(ValueError, match="execution_side_overrides"):
        validate_multi_asset_live_config(replace(original, providers=(invalid, *original.providers[1:])))


@pytest.mark.parametrize("index", [1, 2])
@pytest.mark.parametrize("changed", ["clock", "position"])
def test_inactive_directional_contract_still_rejects_drift(index: int, changed: str) -> None:
    """Observe-only status does not relax what the directional signal can compute."""
    original = load_multi_asset_live_config(NONCRYPTO_PROFILE, mode="observe")
    providers = list(original.providers)
    inactive = replace(providers[index], execution_symbols=())
    providers[index] = (replace(inactive, timeframe="15m") if changed == "clock"
                        else replace(inactive, position_policy="flat_entry_only"))
    with pytest.raises(ValueError, match="directional range route"):
        validate_multi_asset_live_config(replace(original, providers=tuple(providers)))


@pytest.mark.parametrize("index", [1, 2])
def test_inactive_directional_route_keeps_its_own_side_and_stop(index: int) -> None:
    """Execution side scope and stop distance are profile choices, not provider identity."""
    original = load_multi_asset_live_config(NONCRYPTO_PROFILE, mode="observe")
    providers = list(original.providers)
    inactive = replace(providers[index], execution_symbols=(), execution_side_overrides=())
    providers[index] = replace(inactive, execution=replace(inactive.execution, stop_bps=80.0))
    validate_multi_asset_live_config(replace(original, providers=tuple(providers)))


def test_all_inactive_override_families_survive_staging(tmp_path: Path) -> None:
    """Direction, context, stop, sizing and directional lock remain exact stored policy."""
    original = load_multi_asset_live_config("tests/fixtures/profiles/cohort_base.toml", mode="observe")
    provider = replace(original.providers[1], execution_symbols=(),
                       execution_side_overrides=(("BTC", frozenset({"long"})),),
                       entry_context_overrides=(("BTC", "dual_mtf_not_opposed"),),
                       stop_bps_overrides=(("BTC", 60.0),),
                       directional_sizing_overrides=(("BTC", "long", CohortEntrySizing(0.02, 20.0)),),
                       profit_lock_overrides=(CohortProfitLockOverride("BTC", "long", "none"),))
    inactive = replace(original, providers=(original.providers[0], provider, *original.providers[2:]))
    validate_multi_asset_live_config(inactive)
    output = tmp_path / "all-policies.toml"
    stage_cohort_profile(config=inactive, settings=unchanged_settings(inactive), output_path=output)
    staged = load_multi_asset_live_config(output, mode="observe")
    assert staged.providers == inactive.providers
    assert (provider.strategy_id, "BTC") not in staged.executable_provider_symbols
