"""Machine-check the v39-to-v50 six-asset transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-13-v39-v50-transition-contract.md")


def test_runbook_binds_exact_v50_roster_risk_and_observers() -> None:
    """The handoff must name every route and the exact risk evidence."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "multi_asset_growth_first_5000_six_asset_candidate_v50" in text
    assert "375281af0b683e0ddd6c22c02b6a20ea2807705a124a1fce23da76bb39ccc7dd" in text
    assert "v50_growth_sizing_stress_20260813_v1.json" in text
    assert "BTC" in text and "ETH" in text and "SOL" in text and "HYPE" in text
    assert "xyz:SP500" in text and "xyz:SPCX" in text
    assert (
        "six assets, seven provider-symbol routes, and twelve directional scopes"
        in text
    )
    assert "fresh15 v3 observer" in text


def test_runbook_requires_flat_clean_epoch_and_poststart_acceptance() -> None:
    """The first v50 order requires a recoverable 0/0 technical boundary."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "ALL-TIME 0/0" in text and "CURRENT RUN 0/0" in text
    assert "zero venue positions and zero owned orders" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "--accounting-epoch-bundle" in text
    assert "scripts/v50_poststart_acceptance.py" in text
    assert "--enabled" in text and "--i-accept-live-risk" in text
    assert "No new profit target or trailing lock" in text
