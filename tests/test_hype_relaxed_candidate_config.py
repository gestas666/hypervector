"""Staged-profile tests for the HYPE exact-one-blocker strategy tweak."""

from pathlib import Path

import pandas as pd

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.hype_relaxed_one_blocker_provider import (
    HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)

_PROFILE = Path("configs/multi_asset_bidirectional_hype_relaxed_candidate.toml")
_CANONICAL = "hype_breakout_onset_bidirectional_v1"
_RANGE_ONSET = "range_onset_bidirectional_v1"


def test_candidate_profile_changes_entry_contract_only() -> None:
    """The staged tweak preserves sizing and protection while fixing its horizon."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}
    candidate = providers[HYPE_RELAXED_ONE_BLOCKER_STRATEGY]
    hype = next(row for row in config.assets if row.symbol == "HYPE")

    assert candidate.symbols == ("HYPE",)
    assert candidate.sides == frozenset({"long", "short"})
    assert candidate.execution_symbols == ("HYPE",)
    assert candidate.priority == 35
    assert candidate.position_policy == "flat_entry_only"
    assert candidate.priority < providers[_CANONICAL].priority
    assert candidate.execution.stop_bps == 80.0
    assert candidate.execution.target_policy == "none"
    assert candidate.execution.maximum_hold_seconds == 3_600
    assert candidate.execution.maximum_hold_policy == "fixed"
    assert hype.leverage == 5.0
    assert hype.max_notional_usd == 25.0


def test_range_onset_is_retained_for_observation_without_execution_authority() -> None:
    """The next profile must not route the currently unsupported range strategy."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _RANGE_ONSET)

    assert provider.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert provider.execution_symbols == ()
    assert provider.entry_context_overrides == ()
    assert provider.sizing_overrides == ()
    assert not any(
        strategy == _RANGE_ONSET
        for strategy, _symbol in config.executable_provider_symbols
    )


def test_canonical_breakout_wins_a_same_cycle_candidate_conflict() -> None:
    """The relaxed path cannot displace the stronger canonical HYPE onset."""
    router = BidirectionalIntentRouter(
        (
            StrategyCapability(
                HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
                "HYPE",
                frozenset({"long", "short"}),
                35,
                "flat_entry_only",
            ),
            StrategyCapability(
                _CANONICAL,
                "HYPE",
                frozenset({"long", "short"}),
                40,
            ),
        ),
        maximum_positions=1,
    )
    candidate = _intent(HYPE_RELAXED_ONE_BLOCKER_STRATEGY, "short")
    canonical = _intent(_CANONICAL, "long")

    report = router.route(
        (candidate, canonical),
        positions={"HYPE": PositionState("HYPE", None)},
    )

    assert [(row.strategy_id, row.side) for row in report.actions] == [
        (_CANONICAL, "long")
    ]
    assert report.withheld[0].intent.strategy_id == HYPE_RELAXED_ONE_BLOCKER_STRATEGY
    assert report.withheld[0].reason == "lower_provider_priority"


def test_candidate_cannot_close_an_existing_hype_position() -> None:
    """The entry challenger has no implicit cross-strategy exit authority."""
    router = BidirectionalIntentRouter(
        (
            StrategyCapability(
                HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
                "HYPE",
                frozenset({"long", "short"}),
                35,
                "flat_entry_only",
            ),
        ),
        maximum_positions=1,
    )

    report = router.route(
        (_intent(HYPE_RELAXED_ONE_BLOCKER_STRATEGY, "short"),),
        positions={"HYPE": PositionState("HYPE", "long")},
    )

    assert report.actions == ()
    assert report.withheld[0].reason == "provider_flat_entry_only"


def test_default_poller_constructs_every_candidate_provider(tmp_path: Path) -> None:
    """The staged profile has a concrete collector for every declared provider."""
    dependency = tmp_path / "backtest_lab"
    dependency.mkdir()
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda *_args, **_kwargs: pd.DataFrame(),
        backtest_lab_root=dependency,
    )

    assert poller is not None


def _intent(strategy_id: str, side: str) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=strategy_id,
        symbol="HYPE",
        side=side,
        decision_time_ms=1_785_862_320_000,
        reference_price=55.0,
        reason="test",
    )
