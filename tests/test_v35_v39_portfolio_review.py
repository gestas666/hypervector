"""Accuracy contract for the v35/v39 portfolio evidence review."""

from pathlib import Path


_REVIEW = Path("docs/reviews/2026-08-11-v35-v39-v40-live-portfolio-review.md")


def test_review_does_not_overclaim_missing_pressure_root_cause() -> None:
    """Missing L2 diagnosis must remain provisional until v39 reports status."""
    text = _REVIEW.read_text(encoding="utf-8")

    assert "root cause remains unproven" in text
    assert "pressure_status" in text
    assert "v35_live_audit_goal_continuation_20260811T0410Z.json" in text
    assert "v35_live_audit_delta_20260811T0350Z_20260811T0410Z.json" in text
    assert "The missing fields were traced to a live timing defect" not in text


def test_review_captures_sndk_stop_and_latest_transition_boundary() -> None:
    """Review must preserve the resolved close and current three blockers."""
    text = _REVIEW.read_text(encoding="utf-8")

    assert "v35_live_prefix_review_20260811T0520Z.json" in text
    assert "v39_current_500_preflight_20260811T0525Z.json" in text
    assert "v35_live_audit_after_sndk_stop_20260811T0542Z.json" in text
    assert "v39_current_500_preflight_after_sndk_stop_20260811T0544Z.json" in text
    assert "Three positions prevent a profile restart" in text
    assert "SNDK protective stop filled at 1254.2" in text
    assert "-$0.598573 net" in text
    assert "four owned orders" in text


def test_review_remains_within_project_file_limit() -> None:
    """The durable review must stay concise enough for agent inspection."""
    assert len(_REVIEW.read_text(encoding="utf-8").splitlines()) <= 500


def test_review_records_v41_connected_family_concentration() -> None:
    """Per-slot normalization must not be misreported as correlation control."""
    text = _REVIEW.read_text(encoding="utf-8")

    assert "v41_provider_family_concentration_20260811T0535Z_v1.json" in text
    assert "50.0853%" in text
    assert "venue-risk-only" in text
    assert "does not control joint-loss probability" in text
