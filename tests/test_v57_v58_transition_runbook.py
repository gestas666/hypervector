"""Machine-check the proposed V57-to-V58 eight-asset transition."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-19-v57-v58-transition-contract.md")


def test_v58_transition_is_eight_asset_recoverable_and_fail_closed() -> None:
    """The runbook must bind exact topology, accounting, safety, and rollback."""
    text = _RUNBOOK.read_text()

    for symbol in (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    ):
        assert symbol in text
    assert "4 crypto and 4 non-crypto" in text
    assert "46%" in text
    assert "$180.3042" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "v58_eight_asset_incremental_8a04636c_r1" in text
    assert "scripts/v58_poststart_acceptance.py" in text
    assert "<V58_RUN_ID_FROM_STARTUP>" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "--mode monitor" in text
    assert "ALL-TIME 0/0" in text
    assert "Rollback" in text
    assert "explicit live approval" in text
