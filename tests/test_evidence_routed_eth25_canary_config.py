"""Contract tests for the inactive ETH25 breakout-transfer canary profile."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live import multi_asset_default_collectors as default_collectors
from hypervector.live import multi_asset_intent_poller as intent_poller
from hypervector.live.eth_breakout_transfer_provider import EthBreakoutTransferCollector
from hypervector.live.multi_asset_intent_poller import ConfiguredMultiAssetIntentPoller
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_V11 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_V12 = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12.toml"
)
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_ETH = "eth_breakout_precompression_pullback_bidirectional_v1"


def test_v12_changes_only_eth_transfer_execution_scope_and_profile_identity() -> None:
    """The inactive candidate preserves v11 except for bounded ETH authority."""
    prior = load_multi_asset_live_config(_V11, mode="observe")
    candidate = load_multi_asset_live_config(_V12, mode="observe")
    prior_providers = {row.strategy_id: row for row in prior.providers}
    providers = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == (
        "multi_asset_bidirectional_evidence_routed_hype75_eth25_canary_v12"
    )
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in prior.assets
    )
    assert candidate.maximum_positions == prior.maximum_positions == 4
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_HYPE, "HYPE"),
        (_ETH, "ETH"),
    }
    assert providers[_ETH] == replace(
        prior_providers[_ETH],
        execution_symbols=("ETH",),
    )
    for strategy_id in set(providers).difference({_ETH}):
        assert providers[strategy_id] == prior_providers[strategy_id]


def test_v12_keeps_both_eth_sides_and_the_reproduced_exit_contract() -> None:
    """The staged ETH canary retains the audited bidirectional 60bps/12h shape."""
    config = load_multi_asset_live_config(
        _V12,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    provider = next(row for row in config.providers if row.strategy_id == _ETH)

    config.require_live_start(credentials_present=True)
    assert provider.sides == frozenset({"long", "short"})
    assert provider.executable_sides("ETH") == frozenset({"long", "short"})
    assert provider.execution_symbols == ("ETH",)
    assert provider.execution.stop_policy == "fixed_bps"
    assert provider.execution.stop_bps == 60.0
    assert provider.execution.target_policy == "none"
    assert provider.execution.maximum_hold_seconds == 43_200


def test_v12_builds_runtime_collectors_and_retains_low_confidence_evidence() -> None:
    """Execution scope does not inflate the candidate's research confidence."""
    config = load_multi_asset_live_config(_V12, mode="observe")
    evidence = next(
        row
        for row in strategy_evidence_payloads(config.providers)
        if row["strategy_id"] == _ETH and row["symbol"] == "ETH"
    )

    ConfiguredMultiAssetIntentPoller.with_default_collectors(
        config=config,
        fetch_bars=lambda symbol, timeframe, days, *, end_ms=None: None,
        backtest_lab_root=Path("../backtest-lab/backtest_lab").resolve(),
    )
    assert evidence["research_state"] == "prospective_requalification_open_long_only"
    assert evidence["confidence"] == "low"
    assert evidence["evidence_source"] == (
        "docs/research-journal/eth-breakout-precompression-pullback-v17.json"
    )
    assert evidence["execution_effect"] == "report_only"


@pytest.mark.parametrize(("mode", "expected"), [("observe", False), ("live", True)])
def test_v12_binds_eth_readiness_authority_to_runtime_mode(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: bool,
) -> None:
    """The default factory must not label an observer as armed or an arm as inert."""
    config = load_multi_asset_live_config(
        _V12,
        mode=mode,
        enabled=mode == "live",
        accepts_live_risk=mode == "live",
    )
    provider = next(row for row in config.providers if row.strategy_id == _ETH)
    observed: list[bool] = []

    def collector_factory(*, execution_enabled: bool) -> EthBreakoutTransferCollector:
        observed.append(execution_enabled)
        return EthBreakoutTransferCollector(execution_enabled=execution_enabled)

    monkeypatch.setattr(
        default_collectors.eth_transfer,
        "EthBreakoutTransferCollector",
        collector_factory,
    )

    intent_poller._default_collector(
        provider,
        config,
        Path("../backtest-lab/backtest_lab").resolve(),
    )

    assert observed == [expected]
