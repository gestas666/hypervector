"""Machine-check the v52-to-v53 HYPE freshness transition contract."""

from pathlib import Path

_RUNBOOK = Path("docs/runbooks/2026-08-17-v52-v53-transition-contract.md")
_PROFILE = "multi_asset_growth_first_5000_hype_freshness_repair_v53"
_FINGERPRINT = "f6378e473088b962724176f1b4aaf0857d4e2a6c3bf0103c2d1794d6bfd46a82"


def test_runbook_binds_exact_successor_and_single_repair() -> None:
    """The transition must preserve v52 except for HYPE evidence freshness."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert _PROFILE in text
    assert _FINGERPRINT in text
    assert "maximum_hold_evidence_maximum_age_seconds = 60" in text
    assert "v53_growth_sizing_stress_20260817_v1.json" in text
    assert "$92.792193" in text
    assert "1.855844%" in text
    assert "only strategy-contract delta" in text


def test_runbook_requires_exact_flat_epoch_and_acceptance() -> None:
    """No v53 order may precede a recoverable flat transition boundary."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "scripts/cohort_legacy_flat_stop.py" in text
    assert "zero venue positions and zero owned orders" in text
    assert "v53_final_flat_preflight_20260817_v3.json" in text
    assert "v53_hype_freshness_f6378e4_r2" in text
    assert "transition_drain_20260817T044502Z" in text
    assert "scripts/cohort_accounting_rollover.py" in text
    assert "scripts/v53_poststart_acceptance.py" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "ALL-TIME 0/0" in text
    assert "CURRENT RUN 0/0" in text
    assert "Rollback" in text


def test_runbook_provides_final_attach_only_tui_command() -> None:
    """The operator command must attach to v53 without execution authority."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "--mode monitor" in text
    assert (
        "--config configs/multi_asset_growth_first_5000_hype_freshness_repair_v53.toml"
        in text
    )
    assert "--accounting-epoch-bundle" in text
    assert "--refresh-ms 500" in text
    assert "attach-only" in text
