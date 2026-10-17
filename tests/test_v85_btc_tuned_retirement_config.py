"""Acceptance contract for retiring only the unsupported BTC tuned route."""

from __future__ import annotations

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V80 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80.toml"
)
_V85 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85.toml"
)
_TUNED = "hulk_expansion_short_tuned_v2"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")


def test_v85_retires_only_tuned_btc_execution_and_keeps_every_asset_tradable() -> None:
    """The evidence repair must remove one route, not shrink the asset roster."""
    prior = load_multi_asset_live_config(_V80, mode="observe")
    candidate = load_multi_asset_live_config(_V85, mode="observe")

    assert candidate.symbols == _SYMBOLS
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert {
        symbol
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    } == set(_SYMBOLS)
    assert len(candidate.executable_provider_directions) == 8

    prior_by_id = {provider.strategy_id: provider for provider in prior.providers}
    candidate_by_id = {
        provider.strategy_id: provider for provider in candidate.providers
    }
    assert candidate_by_id.keys() == prior_by_id.keys()
    for strategy_id, provider in prior_by_id.items():
        expected = (
            replace(provider, execution_symbols=(), sizing_overrides=())
            if strategy_id == _TUNED
            else provider
        )
        assert candidate_by_id[strategy_id] == expected


@pytest.mark.evidence
def test_v85_approval_names_exactly_one_retired_execution_scope() -> None:
    """The immutable transition approval must bind V80 directly to V85."""
    prior = load_multi_asset_live_config(_V80, mode="observe")
    candidate = load_multi_asset_live_config(_V85, mode="observe")

    evidence = validate_profile_change_approval(
        prior,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == [
        "hulk_expansion_short_tuned_v2|BTC|short"
    ]
    assert evidence["replacement_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"
