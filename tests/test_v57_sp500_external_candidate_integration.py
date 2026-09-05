"""SP500 frozen-source candidate integration for the V57 research loop."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from hypervector.research.cohort_external_asset_pipeline import (
    load_external_asset_pipeline,
)


ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "configs/research/v51_external_asset_pipeline.json"


def test_default_external_catalog_tracks_sp500_frozen_source_lane() -> None:
    """The repaired SP500 observer must remain visible without live authority."""
    payload = json.loads(CATALOG.read_text())
    candidate = next(
        row for row in payload["candidates"] if row["symbol"] == "xyz:SP500"
    )

    assert candidate["stage"] == "frozen_source_native_lifecycle_collection_v1"
    assert candidate["observer_path"].endswith(
        "data/runtime/research/xyz_sp500_fresh15_v3_latest.json"
    )
    epoch = candidate["comparable_decision_epoch"]
    assert epoch["decision_start_ms"] == 1_787_103_000_000
    assert epoch["journal_path"].endswith(
        "data/live/research/xyz_sp500_fresh15_v3_decisions.jsonl"
    )
    assert candidate["lifecycle_status_path"].endswith(
        "data/runtime/research/v58_sp500_fresh15_first_lifecycle_latest.json"
    )
    partial = candidate["partial_lifecycle_source"]
    partial_path = (CATALOG.parent / partial["path"]).resolve()
    partial_raw = partial_path.read_bytes()
    assert partial["bytes"] == len(partial_raw)
    assert partial["sha256"] == sha256(partial_raw).hexdigest()
    assert len(candidate["immutable_evidence"]) == 2
    for evidence in candidate["immutable_evidence"]:
        source = (CATALOG.parent / evidence["path"]).resolve()
        raw = source.read_bytes()
        assert evidence["bytes"] == len(raw)
        assert evidence["sha256"] == sha256(raw).hexdigest()


def test_default_pipeline_surfaces_sp500_open_lifecycle_without_pnl() -> None:
    """The central digest lane must expose the censored SP500 evidence."""
    pipeline = load_external_asset_pipeline(
        CATALOG,
        observed_at=datetime(2100, 1, 1, tzinfo=UTC),
        maximum_observer_age_seconds=1_000_000_000_000.0,
    )

    candidate = next(
        row for row in pipeline.status["candidates"] if row["symbol"] == "xyz:SP500"
    )
    partial = candidate["partial_lifecycle_evidence"]
    prospective = candidate["prospective_lifecycle"]
    assert prospective["watch_state"] == "LIFECYCLE_REPLAY_CANDIDATE_DUE"
    assert prospective["nominal_resolved"] == 0
    assert prospective["nominal_censored"] == 1
    assert prospective["nominal_net_usd_excluding_funding"] == 0.0
    assert prospective["pnl_claimed"] is False
    assert prospective["live_change_supported"] is False
    assert partial["evidence_state"] == "open_censored_lifecycle"
    assert partial["side"] == "short"
    assert partial["nominal_completed"] == 0
    assert partial["nominal_censored"] == 1
    assert partial["pnl_claimed"] is False
    assert partial["live_change_supported"] is False
    source = pipeline.evidence["candidates"]["xyz:SP500"]
    assert source["partial_lifecycle_evidence"]["sha256"] == (
        "2bccf95ea9ea499b461f88d20d754987280c90d79cd9af3c9cc67eb34d463339"
    )
