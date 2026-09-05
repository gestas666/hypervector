"""Machine-check the approved same-profile v51 technical restart contract."""

from pathlib import Path


_RUNBOOK = Path("docs/runbooks/2026-08-14-v51-approved-technical-fix-restart.md")
_PROFILE = "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51"
_FINGERPRINT = "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
_EPOCH = (
    "data/backups/bidirectional_cohort/accounting_epochs/v51_first_live_f9ab743_2030"
)


def _runbook_text() -> str:
    return " ".join(_RUNBOOK.read_text(encoding="utf-8").split())


def test_restart_runbook_binds_exact_approval_and_unchanged_profile() -> None:
    """The boundary may deploy only the three explicitly approved fixes."""
    text = _runbook_text()

    assert _PROFILE in text
    assert _FINGERPRINT in text
    assert "v51-approved-technical-fixes-flat-boundary-v1.json" in text
    assert "V51_ENTRY_FRESHNESS_AT_SUBMISSION_V1" in text
    assert "V51_CROSS_NAMESPACE_EXPOSURE_TELEMETRY_V1" in text
    assert "v51-opposite-exit-precedence-v1.json" in text
    assert "V51_OPPOSITE_EXIT_PRECEDENCE_V1" in text
    assert "No strategy or risk configuration changes are authorized" in text
    assert "do not manually close HYPE for this deployment" in text


def test_restart_runbook_requires_flat_order_free_normal_stop() -> None:
    """Restart must fail closed until all exposure and owned orders are absent."""
    text = _runbook_text()

    assert "all six venue positions are flat" in text
    assert "zero cohort-owned entry, stop, target, and close orders" in text
    assert "exit the supervising tui normally" in text.lower()
    assert "TUI supervisor, backend, and checkpoint writer have exited" in text
    assert "scripts/multi_asset_bidirectional_live_audit.py" in text
    assert "automatic restart is prohibited" in text.lower()


def test_restart_runbook_preserves_epoch_and_requires_verified_backup() -> None:
    """A same-profile technical restart must continue the first-live epoch."""
    text = _runbook_text()

    assert _EPOCH in text
    assert "reuse the existing accounting epoch" in text
    assert "Do not run `scripts/cohort_accounting_rollover.py`" in text
    assert "must not reset CURRENT RUN or ALL-TIME metrics" in text
    assert "scripts/cohort_prechange_backup.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text


def test_restart_runbook_restores_required_index_observers_before_preflight() -> None:
    """A v51 restart cannot proceed with stale SP500 or SPCX source journals."""
    text = _runbook_text()

    command = "scripts/index_hip3_breakout_shadow_observe.py"
    assert text.count(command) >= 2
    assert "--symbol xyz:SP500" in text
    assert "--symbol xyz:SPCX" in text
    assert "observer_status_stale" in text
    assert "Do not delete or reset either cursor" in text


def test_restart_runbook_binds_preflight_live_start_and_acceptance() -> None:
    """Commands must preserve exact v51 identity and require both live flags."""
    text = _runbook_text()

    assert "scripts/multi_asset_bidirectional_preflight.py" in text
    assert text.count("--config configs/" + _PROFILE + ".toml") >= 3
    assert "--active-config configs/" + _PROFILE + ".toml" in text
    assert "--accounting-epoch-bundle " + _EPOCH in text
    assert "--enabled" in text
    assert "--i-accept-live-risk" in text
    assert "scripts/v51_poststart_acceptance.py" in text
    assert "latest_checkpoint.json" in text
    assert "TUI" in text
