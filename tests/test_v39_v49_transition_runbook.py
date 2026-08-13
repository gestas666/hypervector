"""Machine-check the v39-to-v49 repaired-growth transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-12-v39-v49-transition-contract.md")


def test_runbook_binds_exact_v49_identity_stop_repair_and_acceptance() -> None:
    """The operator handoff must not silently reuse v48 evidence."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "multi_asset_growth_first_5000_repaired_candidate_v49" in text
    assert "0be937a1a50ca56becefb330f96d770e39863727d1e2832d025474afc489ae5e" in text
    assert "v49_growth_sizing_stress_20260812_v1.json" in text
    assert "ETH" in text and "60 bps" in text
    assert "SOL" in text and "80 bps" in text
    assert "v49_final_flat_preflight.json" in text
    assert "scripts/v49_poststart_acceptance.py" in text
    assert "--enabled" in text and "--i-accept-live-risk" in text
    assert "zero venue positions and zero owned orders" in text


def test_runbook_requires_a_recoverable_clean_v49_accounting_epoch() -> None:
    """The first v49 cockpit must start at zero without destroying v39 history."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "recoverable clean accounting epoch" in text
    assert "ALL-TIME 0/0" in text
    assert "CURRENT RUN 0/0" in text
    assert "cohort_prestart_backup_verify.py" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "--accounting-epoch-bundle" in text
    assert "append-only" in text
    assert "No ledger, checkpoint, or archive is moved" in text
    assert "v49_first_live" in text
