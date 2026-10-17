"""Acceptance contract for the exact seven-asset V76 successor roster."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_profile_change_approval import (
    validate_profile_change_approval,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_read_only_preflight import (
    maximum_executable_margin_fraction,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
    ResearchPendingMarketObserverCollector,
)
from hypervector.live.multi_asset_strategy_evidence import (
    strategy_research_evidence,
)
from hypervector.research.cohort_friction_contracts import modeled_contract

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_validated_roster_candidate_v76.toml"
)
_V68 = Path(
    "configs/multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68.toml"
)
_EXPECTED = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK")
_EXCLUDED = {"xyz:GOLD", "xyz:SP500", "xyz:BRENTOIL"}


def test_v76_has_exact_requested_roster_and_no_excluded_execution_path() -> None:
    """Every requested asset must be visible and every excluded asset unreachable."""
    config = _load()

    assert config.symbols == _EXPECTED
    assert config.maximum_positions == 3
    assert _EXCLUDED.isdisjoint(config.symbols)
    assert all(
        symbol not in _EXCLUDED
        for provider in config.providers
        for symbol in (*provider.symbols, *provider.execution_symbols)
    )
    assert all(
        excluded.removeprefix("xyz:").lower() not in provider.strategy_id.lower()
        for provider in config.providers
        for excluded in _EXCLUDED
    )
    assert {symbol for _, symbol in config.executable_provider_symbols} == {
        "BTC",
        "HYPE",
        "xyz:SNDK",
    }


def test_v76_observe_only_assets_have_both_side_data_without_entry_authority() -> None:
    """Restored assets remain data-complete without pretending they have an edge."""
    config = _load()
    observer = next(
        row
        for row in config.providers
        if row.strategy_id == RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY
    )
    sol = next(
        row
        for row in config.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )
    hype = next(
        row
        for row in config.providers
        if row.strategy_id == "hype_breakout_compression_alignment_bidirectional_v2"
    )

    assert observer.symbols == ("ETH", "ZEC", "xyz:SPCX")
    assert observer.sides == frozenset({"long", "short"})
    assert observer.execution_symbols == ()
    assert sol.symbols == ("SOL",)
    assert sol.execution_symbols == ()
    assert hype.executable_sides("HYPE") == frozenset({"long"})
    assert all(
        {"long", "short"}.issubset(
            side
            for provider in config.providers
            if symbol in provider.symbols
            for side in provider.sides
        )
        for symbol in _EXPECTED
    )


def test_v76_research_observer_cannot_be_given_execution_authority() -> None:
    """A future config edit must fail closed if it arms the placeholder observer."""
    config = _load()
    observer = next(
        row
        for row in config.providers
        if row.strategy_id == RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY
    )
    altered = replace(observer, execution_symbols=("ZEC",))
    providers = tuple(altered if row == observer else row for row in config.providers)
    armed_placeholder = replace(
        config,
        maximum_positions=4,
        providers=providers,
    )

    with pytest.raises(MultiAssetLiveConfigError, match="execution-disabled"):
        validate_multi_asset_live_config(armed_placeholder)


def test_v76_position_cap_cannot_drop_below_executable_asset_count() -> None:
    """Visible observe-only assets must not weaken the three-symbol live cap."""
    config = _load()

    with pytest.raises(MultiAssetLiveConfigError, match="executable asset count"):
        validate_multi_asset_live_config(replace(config, maximum_positions=2))


def test_v76_risk_envelope_excludes_observe_only_asset_sizing() -> None:
    """Preflight max margin must describe reachable execution, not display rows."""
    config = _load()

    assert maximum_executable_margin_fraction(config) == pytest.approx(0.38)


def test_v76_default_collector_materializes_the_research_observer() -> None:
    """The production poller must be able to construct all configured collectors."""
    config = _load()
    observer = next(
        row
        for row in config.providers
        if row.strategy_id == RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY
    )

    collector = build_default_collector(observer, config, Path("../backtest-lab"))

    assert isinstance(collector, ResearchPendingMarketObserverCollector)


def test_v76_observe_only_assets_explain_why_execution_is_withheld() -> None:
    """TUI evidence must not label deliberate fail-closed routes as unreviewed."""
    expected = {
        "ETH": "tested_families_rejected_new_mechanism_required",
        "ZEC": "development_positive_largest_winner_dependent",
        "xyz:SPCX": "side_timing_set_falsified_new_mechanism_required",
    }

    for symbol, state in expected.items():
        evidence = strategy_research_evidence(
            RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
            symbol,
        )
        assert evidence.research_state == state
        assert evidence.execution_effect == "report_only"
        assert "v76_seven_asset_roster" in evidence.evidence_source


def test_v76_sndk_evidence_distinguishes_predecessor_from_exact_v3() -> None:
    """SNDK's current identity must not inherit predecessor closes as exact."""
    evidence = strategy_research_evidence(
        "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3",
        "xyz:SNDK",
    )

    assert evidence.research_state == "entry_contract_discrepancy_confirmed"
    assert "predecessor n2; exact v3 n0" in evidence.cadence
    assert evidence.evidence_source.endswith(
        "portfolio-overhaul-sndk-onset-fidelity-20260905-v1.json"
    )


def test_v76_sndk_identity_retains_its_source_bound_execution_model() -> None:
    """An identity-only route split must preserve exact SNDK friction mechanics."""
    contract = modeled_contract(
        "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3",
        "xyz:SNDK",
    )

    assert contract is not None
    assert contract.entry_fee_bps == pytest.approx(0.864)
    assert contract.entry_slippage_bps == pytest.approx(4.107450915961097)
    assert contract.stop_policy == "fixed_bps"
    assert contract.stop_bps == pytest.approx(80.0)
    assert contract.maximum_hold_seconds == 86_400
    assert contract.target_policy == "none"
    assert contract.evidence_source.endswith(
        "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
    )


@pytest.mark.evidence
def test_v76_operator_approval_binds_retirement_and_sndk_replacement() -> None:
    """The exact profile change must authenticate both removed execution scopes."""
    previous = load_multi_asset_live_config(_V68, mode="observe")
    candidate = _load()

    evidence = validate_profile_change_approval(
        previous,
        candidate,
        candidate.transition_approval,
    )

    assert evidence["state"] == "approved_profile_change"
    assert evidence["retired_execution_scopes"] == [
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK|short",
        "hype_breakout_compression_alignment_bidirectional_v2|HYPE|short",
    ]
    assert evidence["replacement_execution_scopes"] == [
        "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3|xyz:SNDK|short"
    ]
    assert evidence["execution_authority"] == "none"


def _load() -> MultiAssetLiveConfig:
    """Load the exact successor without constructing a venue client."""
    return load_multi_asset_live_config(
        _CONFIG,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
