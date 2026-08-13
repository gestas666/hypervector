"""Contract tests for the range-retired flat-boundary cohort candidate."""

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ACTIVE = Path("configs/multi_asset_bidirectional_canary.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_range_retired_candidate.toml")
_SELECTIVE_HYPE = Path(
    "configs/multi_asset_bidirectional_range_retired_hype75_candidate.toml"
)
_RANGE = "range_onset_bidirectional_v1"
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_SOL_ALIGNED_RANGE = "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
_FAILED_TARGET20 = "hype_breakout_relaxed_target20_60m_bidirectional_v3"


def test_range_retired_candidate_changes_only_range_execution_authority() -> None:
    """The candidate must preserve the active cohort except range execution."""
    active = load_multi_asset_live_config(_ACTIVE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    active_providers = {row.strategy_id: row for row in active.providers}
    candidate_providers = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == "multi_asset_bidirectional_range_retired_v3"
    assert candidate.symbols == active.symbols
    assert candidate.maximum_positions == active.maximum_positions
    assert candidate_providers.keys() == active_providers.keys()
    assert _FAILED_TARGET20 not in candidate_providers
    assert candidate.executable_provider_symbols == (
        active.executable_provider_symbols
        - {(_RANGE, symbol) for symbol in active.symbols}
    )

    for strategy_id, provider in candidate_providers.items():
        if strategy_id != _RANGE:
            assert provider == active_providers[strategy_id]

    active_range = active_providers[_RANGE]
    candidate_range = candidate_providers[_RANGE]
    assert candidate_range.execution_symbols == ()
    assert (
        replace(
            candidate_range,
            execution_symbols=active_range.execution_symbols,
            entry_context_overrides=active_range.entry_context_overrides,
            sizing_overrides=active_range.sizing_overrides,
        )
        == active_range
    )


def test_target20_static_evidence_records_the_resolved_adverse_n3() -> None:
    """The frozen evidence card must not preserve the superseded N2 result."""
    from hypervector.live.multi_asset_strategy_evidence import (
        strategy_research_evidence,
    )

    evidence = strategy_research_evidence(_FAILED_TARGET20, "HYPE")

    assert evidence.research_state == "prospective_target_first_falsified_n3"
    assert evidence.confidence == "low"
    assert "-15.5073 bps" in evidence.summary
    assert "PF 0.6738" in evidence.summary
    assert "2W/1L" in evidence.summary
    assert "long-only" in evidence.summary


def test_selective_candidate_preserves_baseline_with_only_hype_allocation() -> None:
    """The next-flat profile isolates HYPE sizing without the failed SOL route."""
    baseline = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    selective = load_multi_asset_live_config(_SELECTIVE_HYPE, mode="observe")
    baseline_assets = {row.symbol: row for row in baseline.assets}
    selective_assets = {row.symbol: row for row in selective.assets}
    baseline_providers = {row.strategy_id: row for row in baseline.providers}
    selective_providers = {row.strategy_id: row for row in selective.providers}

    assert selective.profile_id == "multi_asset_bidirectional_range_retired_hype75_v8"
    assert selective.executable_provider_symbols == baseline.executable_provider_symbols
    assert selective.maximum_positions == baseline.maximum_positions
    assert selective_providers.keys() == baseline_providers.keys()

    for symbol, asset in selective_assets.items():
        expected_cap = (
            75.0 if symbol == "HYPE" else baseline_assets[symbol].max_notional_usd
        )
        assert asset.max_notional_usd == expected_cap
        assert (
            replace(
                asset,
                parent_profile_id=baseline.profile_id,
                max_notional_usd=baseline_assets[symbol].max_notional_usd,
            )
            == baseline_assets[symbol]
        )

    for strategy_id, provider in selective_providers.items():
        if strategy_id not in {_HULK, _RANGE, _HYPE_BREAKOUT}:
            assert provider == baseline_providers[strategy_id]

    canonical_hype = selective_providers[_HYPE_BREAKOUT]
    assert canonical_hype.entry_sizing("HYPE") is None
    assert canonical_hype.execution.maximum_hold_seconds == 28_800
    assert canonical_hype.execution.maximum_hold_policy == (
        "extend_while_regime_supported"
    )
    assert canonical_hype.execution.hard_maximum_hold_seconds == 86_400
    assert canonical_hype == baseline_providers[_HYPE_BREAKOUT]
    pinned_hulk = selective_providers[_HULK].entry_sizing("HYPE")
    assert pinned_hulk is not None
    assert pinned_hulk.margin_fraction == 0.03
    assert pinned_hulk.max_notional_usd == 25.0
    assert selective_providers[_RANGE].execution_symbols == ()
    assert selective_providers[_RANGE].entry_sizing("HYPE") is None


def test_selective_candidate_excludes_falsified_sol_live_experiment() -> None:
    """PF below one removes the SOL challenger from next-flat execution scope."""
    selective = load_multi_asset_live_config(_SELECTIVE_HYPE, mode="observe")
    providers = {row.strategy_id: row for row in selective.providers}

    assert _SOL_ALIGNED_RANGE not in providers
    assert (_SOL_ALIGNED_RANGE, "SOL") not in selective.executable_provider_symbols
    assert (_SOL_ALIGNED_RANGE, "SOL") not in selective.provider_entry_sizing
