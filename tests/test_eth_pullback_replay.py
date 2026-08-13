"""Contract tests for the reusable ETH precompression-pullback replay."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from hypervector.research import eth_pullback_replay as replay


def test_replay_uses_exact_live_candidate_contract(monkeypatch: object) -> None:
    """The shared replay helper must match the executable ETH provider."""
    market = pd.DataFrame({"entry_side": ["long"]})
    features = pd.DataFrame({"feature": [1.0]})
    filtered = pd.DataFrame({"entry_side": ["long"]})
    expected = SimpleNamespace(trades=())
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        replay,
        "build_hype_exit_market",
        lambda bars, funding: (market, {"rows": len(bars)}),
    )
    monkeypatch.setattr(
        replay,
        "build_hype_entry_features",
        lambda value: features,
    )

    def apply_policy(
        value: pd.DataFrame,
        feature_rows: pd.DataFrame,
        policy: object,
    ) -> tuple[pd.DataFrame, object]:
        captured["policy"] = policy
        assert value is market
        assert feature_rows is features
        return filtered, SimpleNamespace(eligible_signals=1)

    def replay_exits(
        value: pd.DataFrame,
        policy: object,
        config: object,
    ) -> object:
        captured["exit_policy"] = policy
        captured["config"] = config
        assert value is filtered
        return expected

    monkeypatch.setattr(replay, "apply_hype_entry_policy", apply_policy)
    monkeypatch.setattr(replay, "replay_hype_breakout_exits", replay_exits)

    result = replay.replay_eth_precompression_pullback(
        pd.DataFrame({"close": [100.0]}),
        pd.DataFrame({"funding_rate": [0.0]}),
    )

    assert result.report is expected
    assert result.market is filtered
    assert result.market_evidence == {"rows": 1}
    assert result.policy_evidence.eligible_signals == 1
    assert captured["policy"].require_nonpositive_body is True
    assert captured["policy"].maximum_prior_bbwp_min_15m == 40.0
    assert captured["exit_policy"].policy_id == (
        "eth_breakout_precompression_pullback_bidirectional_v1"
    )
    config = captured["config"]
    assert config.stop_bps == 60.0
    assert config.maximum_hold_minutes == 720
    assert config.fee_bps_per_side == 4.5
    assert config.slippage_bps_per_side == 2.0
