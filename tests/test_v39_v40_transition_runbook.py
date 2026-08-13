"""Machine-checked contract for staged v39 and growth v40/v41."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/runbooks/2026-08-10-v39-v40-transition-contract.md")
_ACTIVE = Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml")
_CURRENT = Path(
    "configs/"
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
_GROWTH_BASELINE = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_candidate_v40.toml"
)
_GROWTH = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_RETIRED = {
    "range_onset_bidirectional_v1",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2",
}


def test_runbook_matches_exact_staged_and_growth_profiles() -> None:
    """Documentation must not drift from the parsed execution contract."""
    active = load_multi_asset_live_config(_ACTIVE, mode="observe")
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    baseline = load_multi_asset_live_config(_GROWTH_BASELINE, mode="observe")
    growth = load_multi_asset_live_config(_GROWTH, mode="observe")
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert active.profile_id in text
    assert current.profile_id in text
    assert baseline.profile_id in text
    assert growth.profile_id in text
    assert current.profile_fingerprint in text
    assert current.symbols == baseline.symbols == growth.symbols
    assert current.providers == baseline.providers == growth.providers
    assert len(current.assets) == 8
    assert len(current.providers) == 7
    assert sum(len(provider.symbols) for provider in current.providers) == 14
    assert (
        sum(
            len(provider.execution_symbols) * len(provider.sides)
            for provider in current.providers
        )
        == 28
    )
    assert all(
        provider.execution_symbols == provider.symbols for provider in current.providers
    )
    assert "xyz:GOLD" not in current.symbols
    assert _RETIRED.isdisjoint(provider.strategy_id for provider in current.providers)


def test_runbook_requires_flat_boundary_and_exact_poststart_audit() -> None:
    """The staged profile must remain inactive and technically observable."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "staged only",
        "report-only candidate",
        "SOL",
        "xyz:GOLD",
        "xyz:SNDK",
        "xyz:SPCX",
        "flat, order-free boundary",
        "scripts/multi_asset_bidirectional_live_audit.py",
        "scripts/v39_poststart_acceptance.py",
        "v39_poststart_negative_control_v35_20260811T0400Z.json",
        "14 provider-symbol routes",
        "28 long/short scopes",
        "execution-incapable",
        "not implicit acceptance gates",
        "latest_current_500_v39_preflight.json",
        "v39_current_500_preflight_20260811T0355Z.json",
        "v39_current_500_preflight_20260811T0525Z.json",
        "v39_current_500_preflight_after_sndk_stop_20260811T0544Z.json",
        "v35_live_audit_after_sndk_stop_20260811T0542Z.json",
        "latest_growth_5000_v40_preflight.json",
        "v40_growth_sizing_stress_20260811T0200Z.json",
        "latest_growth_5000_v41_preflight.json",
        "v40_p99_risk_normalized_exact_reprice_20260811T0226Z_v1.json",
        "`pressure_status`",
    ):
        assert required in text


def test_runbook_preregisters_growth_measurements_without_performance_gates() -> None:
    """The $5k decision must measure friction, repeatability, and co-triggering."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "intent-accounting completeness",
        "fees and funding",
        "share of positive gross market PnL",
        "net PnL excluding the largest winner",
        "cross-symbol entries inside 1, 5, and 15 minutes",
        "maximum concurrent positions",
        "performance outcomes remain report-only",
        "Trade Oracle",
        "contradicted the supplied v39 roster",
        "v41_provider_family_concentration_20260811T0535Z_v1.json",
        "v41_return_panel_coverage_20260811T0558Z_v1.json",
        "growth_5000_v41_preflight_20260811T1718Z.json",
        "v41_successor_readiness_20260811T1730Z_v1.json",
        "scripts/v41_successor_readiness.py",
        "scripts/v41_poststart_acceptance.py",
        "eight assets, not ten",
        "hot reload",
        "58.0238627910263",
        "connected provider clusters",
        "expectancy-weighted sizing",
        "zero exact shared timestamps",
        "covariance weighting remains withheld",
    ):
        assert required in text
