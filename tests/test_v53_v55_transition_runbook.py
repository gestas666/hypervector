"""Machine-check the incremental v53-to-v55 transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-18-v53-v55-transition-contract.md")


def test_v55_transition_is_additive_recoverable_and_fail_closed() -> None:
    """The runbook must preserve v53 routes and gate live arming technically."""
    text = _RUNBOOK.read_text()

    assert "BTC and HYPE remain unchanged" in text
    assert "xyz:SPCX" in text
    assert "3.9 development trades/week" in text
    assert "11 of 20" in text
    assert "NOT_SUITABLE_TECHNICALLY_UNRESOLVED" in text
    assert "e497523e4783e5100847f257c7588c4b" in text
    assert "v53_drain_final_checkpoint.json" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "scripts/v55_poststart_acceptance.py" in text
    assert "v55_final_flat_preflight_20260818_v5.json" in text
    assert "v55_spcx_cash_open_e918f81_r2" in text
    assert "--run-id bidirectional-live-1787048825207" in text
    assert "v55_poststart_acceptance_20260818T103754Z.json" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "--mode monitor" in text
    assert "Rollback" in text
