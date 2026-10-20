"""Contract tests for the evidence-routed HYPE75 extension candidate."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_BASE = Path("tests/fixtures/profiles/range_retired_hype75.toml")
_CANDIDATE = Path(
    "tests/fixtures/profiles/evidence_routed_hype75_extension.toml"
)
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_HYPE = "hype_breakout_onset_bidirectional_v1"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"


def test_candidate_changes_only_provider_execution_scope() -> None:
    """The portfolio route change preserves HYPE sizing and lifecycle semantics."""
    base = load_multi_asset_live_config(_BASE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    base_providers = {row.strategy_id: row for row in base.providers}
    providers = {row.strategy_id: row for row in candidate.providers}

    assert candidate.profile_id == "fixture_evidence_routed_hype75_extension"
    assert candidate.symbols == base.symbols
    assert candidate.maximum_positions == base.maximum_positions
    assert candidate.assets == tuple(
        replace(asset, parent_profile_id=candidate.profile_id) for asset in base.assets
    )
    assert candidate.executable_provider_symbols == {
        (_HULK, "BTC"),
        (_HYPE, "HYPE"),
    }
    assert providers.keys() == base_providers.keys()
    assert all(row.sides == frozenset({"long", "short"}) for row in providers.values())

    for strategy_id, provider in providers.items():
        expected_scope = (
            ("BTC",)
            if strategy_id == _HULK
            else ("HYPE",)
            if strategy_id == _HYPE
            else ()
        )
        assert provider.execution_symbols == expected_scope
        base_provider = base_providers[strategy_id]
        normalized = replace(
            provider,
            execution_symbols=base_provider.execution_symbols,
            sizing_overrides=base_provider.sizing_overrides,
        )
        assert normalized == base_provider

    assert providers[_HULK].sizing_overrides == ()
    assert providers[_SOURCE].execution_symbols == ()
    assert providers[_HYPE].execution.maximum_hold_policy == (
        "extend_while_regime_supported"
    )
    assert providers[_HYPE].execution.hard_maximum_hold_seconds == 86_400
