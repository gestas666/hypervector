"""Evidence-routed v28 candidate configuration contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V27 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml")
_V28 = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v28.toml")
_HT_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"


def test_v28_withholds_only_rejected_sol_ht_breakout_transfer() -> None:
    """SOL must retain both sides through other routes without HT-Breakout."""
    prior = load_multi_asset_live_config(_V27, mode="observe")
    candidate = load_multi_asset_live_config(_V28, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_complete_portfolio_canary_v28"
    )
    assert candidate.profile_fingerprint != prior.profile_fingerprint
    expected_assets = tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.assets == expected_assets
    assert candidate.margin_mode == prior.margin_mode == "isolated"
    assert candidate.maximum_positions == prior.maximum_positions == 9
    assert candidate.cohort_ledger == prior.cohort_ledger
    assert candidate.stop_file == prior.stop_file
    assert candidate.poll_seconds == prior.poll_seconds
    assert candidate.lookback_days == prior.lookback_days
    assert set(after) == set(before)
    assert after[_HT_BREAKOUT] == replace(
        before[_HT_BREAKOUT], execution_symbols=("BTC", "ETH", "HYPE")
    )
    for strategy_id in set(before) - {_HT_BREAKOUT}:
        assert after[strategy_id] == before[strategy_id]

    removed = {(_HT_BREAKOUT, "SOL")}
    assert candidate.executable_provider_symbols == (
        prior.executable_provider_symbols - removed
    )
    for strategy_id in (_HULK, _RANGE):
        provider = after[strategy_id]
        assert "SOL" in provider.execution_symbols
        assert provider.sides == frozenset({"long", "short"})
