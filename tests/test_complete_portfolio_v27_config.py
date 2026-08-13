"""Source-isolated v27 candidate configuration contract."""

from __future__ import annotations

from pathlib import Path
import tomllib

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V26 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml")
_V27 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml")


def test_v27_changes_only_generation_identity_from_v26() -> None:
    """Exit durability must not alter strategy, routing, sizing, or risk."""
    prior = load_multi_asset_live_config(_V26, mode="observe")
    candidate = load_multi_asset_live_config(_V27, mode="observe")
    prior_raw = tomllib.loads(_V26.read_text(encoding="utf-8"))
    candidate_raw = tomllib.loads(_V27.read_text(encoding="utf-8"))

    assert candidate.profile_id == (
        "multi_asset_bidirectional_complete_portfolio_canary_v27"
    )
    assert candidate.profile_fingerprint != prior.profile_fingerprint
    prior_raw.pop("profile")
    candidate_raw.pop("profile")
    assert candidate_raw == prior_raw
    assert candidate.maximum_positions == len(candidate.assets) == 9
    assert len(candidate.executable_provider_symbols) == 24
    declared = {
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    }
    assert candidate.executable_provider_symbols == declared
    assert {
        provider.execution.provider_recipe_exit_policy
        for provider in candidate.providers
    } == {"ignore"}
