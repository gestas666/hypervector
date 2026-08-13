"""Machine-check the v39-to-v51 profit-protected transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-13-v39-v51-transition-contract.md")


def test_runbook_binds_exact_v51_roster_profit_lock_and_risk() -> None:
    """The launch contract must identify the final six-asset successor."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51" in text
    assert "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908" in text
    assert "v51_growth_sizing_stress_20260813_v1.json" in text
    assert "$299.152584" in text
    assert "5.983052%" in text
    assert "100-bps activation" in text
    assert "40-bps minimum locked gain" in text
    assert "80-bps peak giveback" in text
    assert "fresh15-v3" in text


def test_runbook_requires_flat_zero_epoch_and_poststart_audit() -> None:
    """No v51 order may precede the recoverable technical boundary."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "zero venue positions and zero owned orders" in text
    assert "ALL-TIME 0/0" in text
    assert "CURRENT RUN 0/0" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "accounting_epochs/v51_first_live_d022a8a" in text
    assert text.count("--accounting-epoch-bundle") >= 2
    assert "--i-accept-live-risk" in text
    assert "scripts/v51_poststart_acceptance.py" in text


def test_runbook_restarts_both_exact_index_observers_before_preflight() -> None:
    """Launch evidence must come from the reviewed observer implementation."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    command = "scripts/index_hip3_breakout_shadow_observe.py"
    assert text.count(command) >= 2
    assert "--symbol xyz:SP500" in text
    assert "--symbol xyz:SPCX" in text
    assert "preserve their existing cursor" in text
    assert "journal paths" in text
