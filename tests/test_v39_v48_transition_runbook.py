"""Machine-check the v39-to-v48 growth transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-12-v39-v48-transition-contract.md")


def test_runbook_binds_exact_v48_roster_sizing_and_stress() -> None:
    """The runbook must describe the evidence-pruned successor exactly."""
    text = _RUNBOOK.read_text()
    required = (
        "multi_asset_growth_first_5000_repaired_candidate_v48",
        "badda60d549db4fcce9c6a6883198dd71a22f91b58a8073fa5f502c459716f22",
        "v48_growth_sizing_stress_20260812_v1.json",
        "four assets",
        "five provider-symbol routes",
        "eight directional scopes",
        "15% isolated margin",
        "5.89408%",
        "scripts/v48_poststart_acceptance.py",
    )
    for value in required:
        assert value in text


def test_runbook_preserves_flat_boundary_and_rejects_sp500() -> None:
    """No removed route or live command may bypass the transition boundary."""
    text = _RUNBOOK.read_text()
    assert "zero venue positions and zero owned orders" in text
    assert "v48_final_flat_preflight.json" in text
    assert "--staged-config" in text
    assert "--enabled" in text
    assert "--i-accept-live-risk" in text
    assert "SP500 pressure is removed" in text
    assert "report-only redesign" in text
