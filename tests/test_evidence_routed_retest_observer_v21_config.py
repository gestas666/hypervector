"""Contract tests for the inactive evidence-routed v21 candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.hype_breakout_retest_provider import (
    HYPE_BREAKOUT_RETEST_STRATEGY,
    HypeBreakoutRetestCollector,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import (
    MultiAssetLiveConfigError,
)

_V18 = Path("configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml")
_V21 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml"
)


def test_v21_adds_only_retest_observation_and_new_identity() -> None:
    """The next candidate must not widen v18 execution authority."""
    prior = load_multi_asset_live_config(_V18, mode="observe")
    candidate = load_multi_asset_live_config(_V21, mode="observe")
    before = {provider.strategy_id: provider for provider in prior.providers}
    after = {provider.strategy_id: provider for provider in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21"
    )
    assert candidate.maximum_positions == len(candidate.assets) == 4
    assert all(asset.max_positions_per_symbol == 1 for asset in candidate.assets)
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.executable_provider_symbols == prior.executable_provider_symbols
    assert all(
        after[strategy_id] == provider for strategy_id, provider in before.items()
    )
    assert set(after) == set(before) | {HYPE_BREAKOUT_RETEST_STRATEGY}

    retest = after[HYPE_BREAKOUT_RETEST_STRATEGY]
    assert retest.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert retest.sides == frozenset({"long", "short"})
    assert retest.execution_symbols == ()
    assert retest.timeframe == "1m"


def test_v21_builds_prospective_retest_collector_without_execution() -> None:
    """The report-only challenger must construct in the real poller graph."""
    config = load_multi_asset_live_config(_V21, mode="observe")
    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert isinstance(
        poller._collectors[HYPE_BREAKOUT_RETEST_STRATEGY],
        HypeBreakoutRetestCollector,
    )
    assert (HYPE_BREAKOUT_RETEST_STRATEGY, "HYPE") not in (
        config.executable_provider_symbols
    )


def test_v21_remains_fail_closed_without_live_authority() -> None:
    """Observation additions cannot weaken the explicit live-start contract."""
    config = load_multi_asset_live_config(_V21, mode="live")

    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        config.require_live_start(credentials_present=True)
