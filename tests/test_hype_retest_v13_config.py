"""Contract tests for the inactive HYPE retest v13 live profile."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.hype_breakout_retest_provider import (
    HYPE_BREAKOUT_RETEST_STRATEGY,
    HypeBreakoutRetestCollector,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_V11 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_V13 = Path("configs/multi_asset_bidirectional_hype75_retest_v2_eth_observer_v13.toml")
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE_V1 = "hype_breakout_onset_bidirectional_v1"


def test_v13_replaces_only_hype_execution_authority_and_profile_identity() -> None:
    """The staged generation keeps $75 sizing and all non-HYPE policy unchanged."""
    prior = load_multi_asset_live_config(_V11, mode="observe")
    candidate = load_multi_asset_live_config(_V13, mode="observe")
    before = {row.strategy_id: row for row in prior.providers}
    after = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_hype75_retest_v2_eth_observer_v13"
    )
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    hype_asset = next(asset for asset in candidate.assets if asset.symbol == "HYPE")
    assert hype_asset.max_notional_usd == 75.0
    assert hype_asset.leverage == 5.0
    assert candidate.maximum_positions == prior.maximum_positions == 4
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (HYPE_BREAKOUT_RETEST_STRATEGY, "HYPE"),
    }
    assert after[_HYPE_V1] == replace(before[_HYPE_V1], execution_symbols=())
    retest = after[HYPE_BREAKOUT_RETEST_STRATEGY]
    assert retest.execution_symbols == ("HYPE",)
    assert retest.execution == before[_HYPE_V1].execution
    unchanged = set(before).difference({_HYPE_V1})
    assert all(after[strategy] == before[strategy] for strategy in unchanged)


def test_v13_keeps_v1_control_and_builds_v2_runtime_collector() -> None:
    """Both providers evaluate the same feed while only retest v2 may execute."""
    config = load_multi_asset_live_config(_V13, mode="observe")
    poller = ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert _HYPE_V1 in poller._collectors
    assert HYPE_BREAKOUT_RETEST_STRATEGY in poller._collectors
    assert isinstance(
        poller._collectors[HYPE_BREAKOUT_RETEST_STRATEGY],
        HypeBreakoutRetestCollector,
    )


def test_v13_labels_retest_evidence_as_unresolved_live_revision() -> None:
    """A staged policy cannot inherit the old provider's historical edge claim."""
    config = load_multi_asset_live_config(_V13, mode="observe")
    evidence = next(
        row
        for row in strategy_evidence_payloads(config.providers)
        if row["strategy_id"] == HYPE_BREAKOUT_RETEST_STRATEGY
        and row["symbol"] == "HYPE"
    )

    assert evidence["research_state"] == "live_entry_revision_unresolved"
    assert evidence["confidence"] == "low"
    assert evidence["execution_effect"] == "report_only"
