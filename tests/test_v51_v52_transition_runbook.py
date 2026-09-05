"""Machine-check the v51-to-v52 evidence-bound transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-16-v51-v52-transition-contract.md")


def test_runbook_binds_exact_v52_routes_and_risk() -> None:
    """The launch contract must identify the final evidence-bound profile."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "multi_asset_growth_first_5000_evidence_bound_successor_v52" in text
    assert "662d28b352cfc4f09e08c71ee67c8f044421483f2932539b09ea082b5e4f27f7" in text
    assert "v52_growth_sizing_stress_20260816_v1.json" in text
    assert "$92.847534" in text
    assert "1.856951%" in text
    assert "hulk_expansion_short_robust_v3" in text
    assert "liquidity_sweep_long_1h_stop60_target60_v2" in text
    assert "hype_breakout_compression_alignment_bidirectional_v2" in text
    assert "range_onset_bidirectional_v1" in text
    assert "retired" in text.lower()


def test_runbook_requires_flat_epoch_backup_and_fail_closed_start() -> None:
    """No v52 order may precede the recoverable technical boundary."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "zero venue positions and zero owned orders" in text
    assert "ALL-TIME 0/0" in text
    assert "CURRENT RUN 0/0" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "scripts/multi_asset_bidirectional_preflight.py" in text
    assert "scripts/v52_poststart_acceptance.py" in text
    assert "--accounting-epoch-bundle" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "Rollback" in text


def test_runbook_provides_attach_only_staged_tui_command() -> None:
    """The current v51 process must remain monitorable before v52 starts."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "--mode monitor" in text
    assert (
        "--config configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
        in text
    )
    assert (
        "--staged-config configs/multi_asset_growth_first_5000_evidence_bound_successor_v52.toml"
        in text
    )
    assert "--growth-preflight" in text
    assert "attach-only" in text
