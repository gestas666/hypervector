"""The candidate defines seven routes while its research invocation stays disarmed."""

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.hourly_price_provider import HourlyPriceCollector
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    load_multi_asset_live_config,
    validate_multi_asset_live_config,
)
from hypervector.live.multi_asset_polling_contract import SOURCE_TIMEFRAMES
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence

PROFILE = Path("configs/multi_asset_growth_first_5000_noncrypto_research_v89.toml")
BASELINE = Path(
    "configs/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml"
)
ADDITIONS = {"xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL"}


def test_live_package_preserves_researched_contract_and_exact_operator_approval() -> (
    None
):
    """Adding launch provenance cannot silently alter strategy, timing or sizing."""
    from hypervector.live.cohort_profile_change_approval import (
        validate_profile_change_approval,
    )

    original = load_multi_asset_live_config(PROFILE, mode="observe")
    live = load_multi_asset_live_config(
        Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml"),
        mode="observe",
    )
    assert (
        replace(live, transition_approval=None, source_path=original.source_path)
        == original
    )
    baseline = load_multi_asset_live_config(BASELINE, mode="observe")
    evidence = validate_profile_change_approval(
        baseline, live, live.transition_approval
    )
    assert evidence["state"] == "approved_profile_change"
    assert evidence["execution_authority"] == "none"


def test_expansion_adds_three_sources_without_altering_current_execution_contracts() -> (
    None
):
    """Unsupported economics cannot silently inherit V88's operator approval."""
    candidate = load_multi_asset_live_config(PROFILE, mode="observe")
    baseline = load_multi_asset_live_config(BASELINE, mode="observe")
    assert set(candidate.symbols) == set(baseline.symbols) | ADDITIONS
    assert candidate.providers[:4] == baseline.providers
    assert len(candidate.executable_provider_symbols) == 7
    assert set(candidate.executable_provider_symbols).issuperset(
        baseline.executable_provider_symbols
    )
    assert candidate.transition_approval != baseline.transition_approval
    for provider in candidate.providers[4:]:
        assert provider.execution_symbols == provider.symbols
        assert SOURCE_TIMEFRAMES[provider.strategy_id] == "15m"
        assert isinstance(
            build_default_collector(provider, candidate, Path("unused")),
            HourlyPriceCollector,
        )
        assert provider.execution.maximum_hold_seconds == 86400
        assert provider.execution.provider_recipe_exit_policy == "honor"
    with pytest.raises(ValueError):
        candidate.require_live_start(credentials_present=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timeframe", "1m"),
        ("maximum_entry_delay_seconds", 60),
        ("sides", frozenset({"long"})),
    ],
)
def test_hourly_recipe_rejects_runtime_clock_or_direction_drift(
    field: str, value: object
) -> None:
    """The research recipe's timing and symmetric direction are explicit contracts."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    invalid = replace(config.providers[-1], **{field: value})
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(config, providers=(*config.providers[:-1], invalid))
        )


def test_hourly_recipe_rejects_changed_stop_without_a_new_contract() -> None:
    """The screened stop shape cannot be mislabeled as the unchanged recipe."""
    config = load_multi_asset_live_config(PROFILE, mode="observe")
    invalid = replace(
        config.providers[-1],
        execution=replace(
            config.providers[-1].execution,
            maximum_stop_bps=500.0,
        ),
    )
    with pytest.raises(ValueError, match="hourly price"):
        validate_multi_asset_live_config(
            replace(config, providers=(*config.providers[:-1], invalid))
        )


def test_new_tui_rows_report_measured_activity_and_mixed_evidence() -> None:
    """Every new row must disclose historical activity without implying live edge."""
    candidate = load_multi_asset_live_config(PROFILE, mode="observe")
    for provider in candidate.providers[4:]:
        evidence = strategy_research_evidence(provider.strategy_id, provider.symbols[0])
        assert evidence.research_state != "unreviewed_exact_mapping"
        assert evidence.confidence == "low"
        # Evidence is global per route and a later review may supersede a row;
        # the 48-day V89 screen must remain disclosed either as the cadence or
        # inside the superseding summary.
        assert "48 days" in evidence.cadence or "48-day" in evidence.summary
        assert evidence.execution_effect == "report_only"
