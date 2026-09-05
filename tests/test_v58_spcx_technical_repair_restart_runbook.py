"""Machine-check the approval-gated V58 SPCX technical restart contract."""

from pathlib import Path


_RUNBOOK = Path("docs/runbooks/2026-08-21-v58-spcx-technical-repair-restart.md")
_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_EPOCH = (
    "data/backups/bidirectional_cohort/accounting_epochs/"
    "v58_eight_asset_incremental_8a04636c_r2"
)
_APPROVAL = "APPROVE TRANSITION DRAIN AND VERIFIED V58 CORRECTED CUTOVER"


def _text() -> str:
    return " ".join(_RUNBOOK.read_text(encoding="utf-8").split())


def test_restart_requires_exact_approval_and_preserves_profile_contract() -> None:
    """The repair must remain approval-gated and configuration-neutral."""
    text = _text()

    assert _APPROVAL in text
    assert _PROFILE in text
    assert _FINGERPRINT in text
    assert "No configuration change" in text
    assert "No strategy, side, exit, sizing, leverage, or risk change" in text
    assert "No retroactive SPCX entry" in text


def test_restart_drains_then_proves_flat_order_free_and_archives() -> None:
    """The backend may restart only after drain completion and archival."""
    text = _text()

    assert "TRANSITION DRAIN" in text
    assert "all eight assets are flat" in text
    assert "zero owned entry, stop, target, and close orders" in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "--expected-run-id bidirectional-live-1787272893887" in text
    assert "--yes" in text
    assert "scripts/multi_asset_bidirectional_live_audit.py" in text


def test_restart_reuses_r2_epoch_and_forbids_rollover() -> None:
    """A same-profile implementation restart must preserve V58 accounting."""
    text = _text()

    assert _EPOCH in text
    assert "reuse the existing V58 accounting epoch" in text
    assert "Do not run `scripts/cohort_accounting_rollover.py`" in text
    assert "must not reset CURRENT RUN or ALL-TIME metrics" in text
    assert "scripts/cohort_prechange_backup.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text


def test_restart_binds_preflight_start_acceptance_and_monitor() -> None:
    """Every deployment command must retain exact identity and fail closed."""
    text = _text()

    config = f"configs/{_PROFILE}.toml"
    assert "scripts/multi_asset_bidirectional_preflight.py" in text
    assert text.count(f"--config {config}") >= 4
    assert f"--active-config {config}" in text
    assert f"--accounting-epoch-bundle {_EPOCH}" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "scripts/v58_poststart_acceptance.py" in text
    assert "--mode monitor" in text
    assert "cash_open_trade_bars_incomplete" in text
    assert "action-free readiness seed" in text
