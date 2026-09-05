"""Projection of the exact MU independent-window lifecycle status."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.research.cohort_external_lifecycle_status import (
    load_external_lifecycle_status,
)


def test_mu_technical_coverage_gap_is_visible_without_replay_authority(
    tmp_path: Path,
) -> None:
    """A terminal schedule gap must remain report-only instead of crashing."""
    observed_at = datetime(2026, 8, 21, 9, 30, tzinfo=UTC)
    status_path = tmp_path / "mu_lifecycle.json"
    status_path.write_text(json.dumps(_status(observed_at)), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}", encoding="utf-8")

    status, evidence = load_external_lifecycle_status(
        catalog,
        {"lifecycle_status_path": status_path.name},
        "xyz:MU",
        observed_at,
        120.0,
    )

    assert status is not None
    assert status["watch_state"] == "TECHNICAL_COVERAGE_GAP"
    assert status["collection_state"] == "technical_coverage_gap"
    assert status["decision_schedule_complete"] is False
    assert status["lifecycle_replay_candidate_due"] is False
    assert status["live_change_supported"] is False
    assert evidence is not None and evidence["sha256"]


def _status(observed_at: datetime) -> dict[str, object]:
    summary = {
        "resolved": 0,
        "censored": 0,
        "modeled_net_usd_excluding_funding": 0.0,
    }
    return {
        "schema_version": "mu_source_native_independent_window_status_v1",
        "symbol": "xyz:MU",
        "observed_at_ms": int(observed_at.timestamp() * 1_000),
        "watch_state": "TECHNICAL_COVERAGE_GAP",
        "collection_state": "technical_coverage_gap",
        "source": {"observed_decisions": 179, "eligible_decisions": 5},
        "eligible_onsets_by_side": {"long": 3, "short": 2},
        "lifecycle_replay_candidate_due": False,
        "collection_deadline_reached": False,
        "nominal": {"summary": dict(summary)},
        "stress": {"summary": dict(summary)},
        "technical_assessment": {
            "all_observed_paths_resolved": False,
            "decision_schedule_complete": False,
            "live_change_supported": False,
        },
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
