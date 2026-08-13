"""Machine-checked operational contract for the v39-to-v43 transition."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/runbooks/2026-08-11-v39-v43-transition-contract.md")
_ACTIVE = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_"
    "current_canary_v39.toml"
)
_NEXT = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")


def test_runbook_matches_exact_v43_routes_and_directions() -> None:
    """Documentation cannot hide retired routes or widen one-sided BTC arms."""
    active = load_multi_asset_live_config(_ACTIVE, mode="observe")
    candidate = load_multi_asset_live_config(_NEXT, mode="observe")
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert active.profile_id in text
    assert candidate.profile_id in text
    assert candidate.profile_fingerprint in text
    assert set(candidate.symbols) == {"BTC", "HYPE", "xyz:SP500"}
    assert len(candidate.providers) == 4
    assert len(candidate.executable_provider_symbols) == 4
    assert len(candidate.executable_provider_directions) == 6
    for expected in (
        "hulk_expansion_short_robust_v3|BTC|short",
        "liquidity_sweep_long_1h_stop60_v1|BTC|long",
        "hype_breakout_compression_pullback_bidirectional_v1|HYPE|long/short",
        "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500|long/short",
    ):
        assert expected in text


def test_runbook_requires_flat_boundary_and_exact_poststart_acceptance() -> None:
    """The successor remains inactive until technical transition checks pass."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "flat and order-free",
        "explicit live-risk authorization",
        "v43_current_500_preflight_20260811_v1.json",
        "v43_btc_specialist_successor_risk_20260811_v1.json",
        "scripts/v43_poststart_acceptance.py",
        "one exact forward event",
        "repeatability is not established",
        "10-position capacity",
        "three simultaneous positions",
        "23.2036076893%",
        "provider-native target",
        "venue reduce-only stop",
        "opposite executable intent",
        "maximum-hold deadline",
        "no automatic restart",
    ):
        assert required in text
