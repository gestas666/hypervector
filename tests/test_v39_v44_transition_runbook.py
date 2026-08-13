"""Machine-check the exact v39-to-v44 transition contract."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/runbooks/2026-08-11-v39-v44-transition-contract.md")
_ACTIVE = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_"
    "current_canary_v39.toml"
)
_NEXT = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)


def test_runbook_binds_the_corrected_v44_routes() -> None:
    """The operational document must not resurrect removed v39/v43 routes."""
    active = load_multi_asset_live_config(_ACTIVE, mode="observe")
    candidate = load_multi_asset_live_config(_NEXT, mode="observe")
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert active.profile_id in text
    assert candidate.profile_id in text
    assert candidate.profile_fingerprint in text
    assert set(candidate.symbols) == {"BTC", "HYPE", "xyz:SP500"}
    assert len(candidate.providers) == 4
    assert len(candidate.executable_provider_directions) == 6
    for expected in (
        "hulk_expansion_short_robust_v3|BTC|short",
        "liquidity_sweep_long_1h_stop60_target60_v2|BTC|long",
        "hype_breakout_compression_pullback_bidirectional_v1|HYPE|long/short",
        "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500|long/short",
    ):
        assert expected in text


def test_runbook_requires_flat_boundary_and_honest_v44_evidence() -> None:
    """Transition remains manual and exposes unresolved economic evidence."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "flat and order-free",
        "explicit live-risk authorization",
        "v44_current_500_preflight_20260811_v1.json",
        "v44_btc_specialist_successor_risk_20260811_v1.json",
        "v44_portfolio_friction_stress_20260811_v1.json",
        "scripts/v44_poststart_acceptance.py",
        "taker-parity",
        "repeatability is not established",
        "10-position capacity",
        "three simultaneous positions",
        "23.2036076893%",
        "no automatic restart",
        "no profit-lock rule",
    ):
        assert required in text
