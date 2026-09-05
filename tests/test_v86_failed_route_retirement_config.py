"""V86 must stop failed entries without erasing the seven-asset roster."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_accounting_rollover import (
    load_required_accounting_epoch,
)
from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V85 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85.toml"
)
_V86 = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_ROBUST = "hulk_expansion_short_robust_v3"
_ZEC = "zec_donchian_20_10_atr20_long_v1"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")


def test_v86_requires_a_fresh_bound_accounting_epoch() -> None:
    """V86 cannot mix prior losses into its new 0/0 display boundary."""
    config = load_multi_asset_live_config(_V86, mode="observe")

    with pytest.raises(ValueError, match="requires --accounting-epoch-bundle"):
        load_required_accounting_epoch(None, config)


def test_v86_preserves_all_observers_and_retires_only_failed_authority() -> None:
    """V86 must keep route telemetry while blocking the two falsified entries."""
    prior = load_multi_asset_live_config(_V85, mode="observe")
    candidate = load_multi_asset_live_config(_V86, mode="observe")

    assert candidate.symbols == _SYMBOLS
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert len(candidate.providers) == 9
    assert len(candidate.executable_provider_directions) == 6
    assert {symbol for _, symbol in candidate.executable_provider_symbols} == {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SPCX",
        "xyz:SNDK",
    }

    prior_by_id = {provider.strategy_id: provider for provider in prior.providers}
    candidate_by_id = {
        provider.strategy_id: provider for provider in candidate.providers
    }
    assert candidate_by_id.keys() == prior_by_id.keys()
    for strategy_id, provider in prior_by_id.items():
        expected = (
            replace(
                provider,
                execution_symbols=(),
                sizing_overrides=(),
                execution_side_overrides=(),
            )
            if strategy_id in {_ROBUST, _ZEC}
            else provider
        )
        assert candidate_by_id[strategy_id] == expected


def test_v86_approval_binds_both_retirements_without_replacements() -> None:
    """Transition lineage must name exactly the evidence-failed scopes."""
    prior = load_multi_asset_live_config(_V85, mode="observe")
    candidate = load_multi_asset_live_config(_V86, mode="observe")

    evidence = validate_profile_change_approval(
        prior,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["retired_execution_scopes"] == [
        "hulk_expansion_short_robust_v3|BTC|short",
        "zec_donchian_20_10_atr20_long_v1|ZEC|long",
    ]
    assert evidence["replacement_execution_scopes"] == []
    assert evidence["execution_authority"] == "none"
