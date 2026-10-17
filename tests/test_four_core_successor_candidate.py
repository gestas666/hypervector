"""The reviewable core successor preserves each retained production contract."""

import pytest

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.cohort_pressure_dependencies import pressure_dependency_commands
from hypervector.live.cohort_profile_change_approval import validate_profile_change_approval

_BASELINE = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml"
)


@pytest.mark.evidence
def test_candidate_retains_only_fully_executable_core_routes() -> None:
    """Every retained asset has exactly its existing executable provider and side."""
    baseline = load_multi_asset_live_config(_BASELINE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    assert candidate.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert candidate.maximum_positions == len(candidate.assets) == 4
    assert len(candidate.providers) == 4
    for asset in candidate.assets:
        assert replace(asset, parent_profile_id=baseline.profile_id) == next(
            a for a in baseline.assets if a.symbol == asset.symbol
        )
        (provider,) = [p for p in candidate.providers if asset.symbol in p.symbols]
        assert provider == next(
            p for p in baseline.providers if p.strategy_id == provider.strategy_id
        )
        assert provider.execution_symbols == (asset.symbol,)
        expected = "short" if asset.symbol == "SOL" else "long"
        assert provider.executable_sides(asset.symbol) == frozenset({expected})
    assert candidate.poll_seconds == baseline.poll_seconds
    assert candidate.lookback_days == baseline.lookback_days
    assert candidate.network == "mainnet"
    assert candidate.margin_mode == "isolated"
    assert pressure_dependency_commands(candidate) == {}
    assert candidate.transition_approval is not None
    if candidate.transition_approval.exists():
        approval = validate_profile_change_approval(
            baseline, candidate, candidate.transition_approval
        )
        assert approval["state"] == "approved_profile_change"


def test_asset_without_any_declared_provider_still_fails() -> None:
    """Removing placeholder routes cannot permit a retained asset with no source."""
    import pytest
    from hypervector.live.multi_asset_live_config import (
        validate_multi_asset_live_config,
    )

    baseline = load_multi_asset_live_config(_BASELINE, mode="observe")
    missing = replace(
        baseline,
        providers=tuple(p for p in baseline.providers if "BTC" not in p.symbols),
    )
    with pytest.raises(ValueError, match="at least one provider"):
        validate_multi_asset_live_config(missing)


@pytest.mark.evidence
def test_improvement_plan_is_source_bound_and_matches_exact_executable_sides() -> None:
    """The pending monitor must neither inherit old profiles nor widen scope."""
    from test_cohort_improvement_monitor_script import _load
    from hypervector.research.cohort_hypothesis_ledger import merge_hypothesis_ledger

    config = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    monitor = _load()
    overrides, _ = monitor._load_decision_overrides(
        Path("configs/research/cohort_improvement_decision_overrides_v88.json")
    )
    monitor._validate_override_identity(
        overrides,
        {
            "run": {
                "profile_id": config.profile_id,
                "profile_fingerprint": config.profile_fingerprint,
            }
        },
    )
    expected = {
        f"{p.strategy_id}|{symbol}": sorted(p.executable_sides(symbol))
        for p in config.providers
        for symbol in p.execution_symbols
    }
    assert set(overrides["routes"]) == set(expected)
    assert {
        row["route"]: row["required_sides"] for row in overrides["active_hypotheses"]
    } == expected
    ledger = merge_hypothesis_ledger(
        overrides["active_hypotheses"], overrides["hypothesis_decisions"]
    )
    assert len(ledger) == 6
    assert all(row["automatic_live_change"] is False for row in ledger)
