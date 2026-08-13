"""Machine-check the v39-to-v45 growth transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-12-v39-v45-transition-contract.md")


def test_runbook_binds_exact_v45_identity_sizing_and_evidence() -> None:
    """The runbook cannot silently fall back to v44 sizing or dynamic leverage."""
    text = _RUNBOOK.read_text()

    assert "growth_sizing_candidate_v45" in text
    assert "e1b46ba749a46cc2966f0b4629bfd487" in text
    assert "v45_growth_sizing_stress_20260812_v2.json" in text
    assert "13.3333%" in text and "16.6667%" in text
    assert "- HYPE: 7% margin" in text
    assert "- SP500: 7% margin" in text
    assert "telemetry-only" in text
    assert "data/observe/v45_candidate_shadow" in text
    assert "execution authority `none`" in text
    assert "b8ba030a964ed2c109346641e9d91534ada73ec851ae191a318cf3f8bac2bb90" in text
    assert "1.39364%" in text


def test_runbook_requires_flat_preflight_explicit_start_and_acceptance() -> None:
    """No staged view or live command may bypass the flat transition boundary."""
    text = _RUNBOOK.read_text()

    assert "zero venue positions and zero owned orders" in text
    assert "v45_final_flat_preflight.json" in text
    assert "--staged-config" in text
    assert "--mode live" in text
    assert "--enabled" in text
    assert "--i-accept-live-risk" in text
    assert "scripts/v45_poststart_acceptance.py" in text
