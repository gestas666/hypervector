"""Staged-profile contract for the strongest current evidence candidates."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.hype_relaxed_contract import (
    HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_PROFILE = Path("configs/multi_asset_bidirectional_evidence_candidate_v4.toml")
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
_CANONICAL_HYPE = "hype_breakout_onset_bidirectional_v1"


def test_profile_stages_two_independent_bidirectional_candidates() -> None:
    """The next profile retains four assets while narrowing unsupported scope."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}

    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert config.maximum_positions == 4
    assert set(providers) == {
        _HULK,
        _RANGE,
        _SOURCE,
        BTC_STRUCTURAL_FIXED60_STRATEGY,
        HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
        _CANONICAL_HYPE,
    }
    assert all(row.sides == frozenset({"long", "short"}) for row in providers.values())
    assert providers[_RANGE].execution_symbols == ()
    assert providers[_SOURCE].execution_symbols == ()
    assert providers[_CANONICAL_HYPE].execution_symbols == ()
    assert providers[BTC_STRUCTURAL_FIXED60_STRATEGY].execution_symbols == ("BTC",)
    assert providers[HYPE_RELAXED_MATCHED_FIXED_STRATEGY].execution_symbols == ("HYPE",)
    assert len(config.executable_provider_symbols) == 6


def test_candidates_use_fixed_horizon_flat_entry_contracts() -> None:
    """Neither candidate can reverse another strategy's existing position."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}

    for strategy_id, stop_bps in (
        (BTC_STRUCTURAL_FIXED60_STRATEGY, 60.0),
        (HYPE_RELAXED_MATCHED_FIXED_STRATEGY, 80.0),
    ):
        provider = providers[strategy_id]
        assert provider.position_policy == "flat_entry_only"
        assert provider.execution.stop_bps == stop_bps
        assert provider.execution.target_policy == "none"
        assert provider.execution.maximum_hold_seconds == 3_600
        assert provider.execution.maximum_hold_policy == "fixed"


def test_candidate_profile_constructs_every_default_collector(tmp_path: Path) -> None:
    """A declared candidate cannot survive config parsing without an engine."""
    dependency = tmp_path / "backtest_lab"
    dependency.mkdir()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
        backtest_lab_root=dependency,
    )

    assert poller is not None


def test_btc_candidate_wins_same_cycle_but_cannot_reverse() -> None:
    """Evidence priority applies only at a flat BTC entry boundary."""
    router = BidirectionalIntentRouter(
        (
            StrategyCapability(_SOURCE, "BTC", frozenset({"long", "short"}), 30),
            StrategyCapability(
                BTC_STRUCTURAL_FIXED60_STRATEGY,
                "BTC",
                frozenset({"long", "short"}),
                34,
                "flat_entry_only",
            ),
        ),
        maximum_positions=1,
    )
    candidate = _intent(BTC_STRUCTURAL_FIXED60_STRATEGY, "long")
    source = _intent(_SOURCE, "short")

    flat = router.route(
        (source, candidate),
        positions={"BTC": PositionState("BTC", None)},
    )
    open_position = router.route(
        (candidate,),
        positions={"BTC": PositionState("BTC", "short")},
    )

    assert [(row.strategy_id, row.side) for row in flat.actions] == [
        (BTC_STRUCTURAL_FIXED60_STRATEGY, "long")
    ]
    assert open_position.actions == ()
    assert open_position.withheld[0].reason == "provider_flat_entry_only"


def test_profile_identity_is_stable_without_reading_secrets() -> None:
    """Repeated disarmed loads produce one immutable non-secret identity."""
    first = load_multi_asset_live_config(_PROFILE, mode="observe")
    second = load_multi_asset_live_config(_PROFILE, mode="observe")

    assert first.profile_fingerprint == second.profile_fingerprint


def _intent(strategy_id: str, side: str) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=strategy_id,
        symbol="BTC",
        side=side,
        decision_time_ms=1_785_880_000_000,
        reference_price=64_000.0,
        reason="test",
    )
