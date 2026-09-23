"""The V93 proposal binds exit policy v2 everywhere and changes nothing else in V91."""

from dataclasses import replace

from hypervector.live.cohort_adaptive_exit_policy import RETENTION_EXIT_POLICY
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

V91 = "configs/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml"
V93 = "configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml"


def test_v93_is_v91_plus_v2_exits_and_a_25_dollar_budget() -> None:
    original = load_multi_asset_live_config(V91, mode="observe")
    candidate = load_multi_asset_live_config(V93, mode="observe")
    assert (
        original.profile_fingerprint
        == "00ca7e008e8b2ec7cbeac4b9541cabf39a8576a23769b92a169e984616fe8d8c"
    )
    assert (
        candidate.profile_fingerprint
        == "33131f1898d86dda4f5cab2b6091748144f6a81da29b9c9464a644b330dc3e05"
    )
    assert not candidate.enabled and not candidate.accepts_live_risk
    assert str(candidate.transition_approval).endswith("v91-to-v93-exit-policy-v2-20260923-v1.json")
    assert candidate.maximum_positions == original.maximum_positions == 8
    assert [asset.symbol for asset in candidate.assets] == [
        asset.symbol for asset in original.assets
    ]
    for proposed, previous in zip(candidate.providers, original.providers, strict=True):
        assert proposed.execution.adaptive_exit_policy == RETENTION_EXIT_POLICY
        assert proposed.execution.stop_risk_budget == StopRiskBudget(25, 20)
        reverted = replace(
            proposed,
            execution=replace(
                proposed.execution,
                adaptive_exit_policy=previous.execution.adaptive_exit_policy,
                stop_risk_budget=None,
            ),
        )
        assert reverted == previous
