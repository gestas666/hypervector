"""Machine-check the v39-to-v47 repaired-growth transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-12-v39-v47-transition-contract.md")


def test_runbook_binds_exact_v47_routes_sizing_and_stress() -> None:
    """The runbook cannot fall back to v45 or legacy HIP3 v1."""
    text = _RUNBOOK.read_text()

    assert "multi_asset_growth_first_5000_repaired_candidate_v47" in text
    assert "cb1482029e230069bb6615cb5232975728602c3c14b925ef7f0c734a90b1bc0f" in text
    assert "v47_growth_sizing_stress_20260812_v3.json" in text
    assert "fresh15s_bidirectional_v2" in text
    assert "12% isolated margin" in text
    assert "fixed 10x leverage" in text
    assert "five simultaneous positions" in text
    assert "5.73877%" in text
    assert "HT onset ETH/SOL" in text and "removed" in text
    assert "HIP-3 Swing" in text and "removed" in text


def test_runbook_requires_flat_preflight_explicit_start_and_acceptance() -> None:
    """No preview or start may bypass exact flat-boundary evidence."""
    text = _RUNBOOK.read_text()

    assert "zero venue positions and zero owned orders" in text
    assert "v47_final_flat_preflight.json" in text
    assert "--sizing-equity-usd 5000" in text
    assert "--staged-config" in text
    assert "--mode live" in text
    assert "--enabled" in text
    assert "--i-accept-live-risk" in text
    assert "scripts/v47_poststart_acceptance.py" in text
    assert "Rollback is permitted only" in text
    assert "No report-only observer substitutes for the live trial" in text
