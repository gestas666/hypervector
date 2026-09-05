"""Candidate-only configuration tests for restored HYPE-native breakout."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.hype_breakout_cohort_provider import (
    HYPE_BREAKOUT_COHORT_STRATEGY,
)
from hypervector.live.hype_native_breakout_provider import (
    HYPE_NATIVE_BREAKOUT_STRATEGY,
    HypeNativeBreakoutOnsetCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
    SOURCE_TIMEFRAMES,
)
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence

_ROOT = Path(__file__).parents[1]
_CONFIG = (
    _ROOT
    / "configs/multi_asset_growth_first_5000_hype_native_reconstruction_candidate_v54.toml"
)
_COMPRESSION = "hype_breakout_compression_alignment_bidirectional_v2"


def test_candidate_uses_new_hype_only_identity_and_preserves_exit_contract() -> None:
    """The candidate isolates HYPE and retains the original stop/exit timing."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}
    native = providers[HYPE_NATIVE_BREAKOUT_STRATEGY]
    execution = native.execution

    assert config.profile_id.endswith("hype_native_reconstruction_candidate_v54")
    assert native.symbols == ("HYPE",)
    assert native.execution_symbols == ("HYPE",)
    assert native.sides == {"long", "short"}
    assert native.position_policy == "enter_and_close"
    assert execution.stop_policy == "fixed_bps"
    assert execution.stop_bps == 80.0
    assert execution.target_policy == "none"
    assert execution.maximum_hold_seconds == 28_800
    assert execution.maximum_hold_policy == "fixed"
    assert execution.hard_maximum_hold_seconds is None
    assert execution.maximum_hold_evidence_maximum_age_seconds is None
    assert providers[_COMPRESSION].execution_symbols == ()


def test_candidate_scales_one_variable_and_keeps_btc_routes_unchanged() -> None:
    """HYPE starts at a declared 25% notional tier while BTC stays v53-exact."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    assets = {row.symbol: row for row in config.assets}
    providers = {row.strategy_id: row for row in config.providers}

    assert assets["HYPE"].leverage == 5.0
    assert assets["HYPE"].margin_fraction == 0.05
    assert assets["HYPE"].max_notional_usd == 1_250.0
    assert assets["BTC"].leverage == 10.0
    assert assets["BTC"].margin_fraction == 0.10
    assert assets["BTC"].max_notional_usd == 5_000.0
    assert providers["hulk_expansion_short_robust_v3"].execution_symbols == ("BTC",)
    sweep = "liquidity_sweep_long_1h_stop60_target60_v2"
    assert providers[sweep].execution_symbols == ("BTC",)


def test_runtime_registry_builds_only_the_native_hype_collector() -> None:
    """Polling and default assembly recognize the clean provider identity."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_NATIVE_BREAKOUT_STRATEGY
    )
    collector = build_default_collector(provider, config, _ROOT)

    assert isinstance(collector, HypeNativeBreakoutOnsetCollector)
    assert SOURCE_TIMEFRAMES[HYPE_NATIVE_BREAKOUT_STRATEGY] == "1m"
    assert READINESS_SEED_LOOKBACK_MINUTES[HYPE_NATIVE_BREAKOUT_STRATEGY] == 2


def test_candidate_validator_rejects_non_hype_native_scope(tmp_path: Path) -> None:
    """Configuration cannot reintroduce BTC/ETH/SOL transfer authority."""
    malformed = _CONFIG.read_text().replace(
        'strategy_id = "hype_native_breakout_onset_bidirectional_v2"\n'
        'symbols = ["HYPE"]',
        'strategy_id = "hype_native_breakout_onset_bidirectional_v2"\n'
        'symbols = ["BTC", "HYPE"]',
        1,
    )
    target = tmp_path / "invalid.toml"
    target.write_text(malformed)

    with pytest.raises(MultiAssetLiveConfigError, match="HYPE-only"):
        load_multi_asset_live_config(target, mode="observe")


def test_candidate_does_not_reintroduce_the_legacy_transfer_provider() -> None:
    """The contaminated cross-asset identity must not coexist with v54."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    providers = {row.strategy_id: row for row in config.providers}

    assert HYPE_BREAKOUT_COHORT_STRATEGY not in providers
    assert all(
        set(provider.execution_symbols).issubset({"BTC", "HYPE"})
        for provider in config.providers
    )


def test_candidate_evidence_is_exactly_attributed_not_unreviewed() -> None:
    """TUI evidence must show the reconstruction thesis under the new ID."""
    evidence = strategy_research_evidence(HYPE_NATIVE_BREAKOUT_STRATEGY, "HYPE")

    assert evidence.research_state == "live_seed_promising_history_contradictory"
    assert evidence.confidence == "low_to_medium"
    assert "6W/1L" in evidence.summary
    assert evidence.evidence_source.endswith(
        "v54-hype-native-breakout-reconstruction-proposal-v1.json"
    )
