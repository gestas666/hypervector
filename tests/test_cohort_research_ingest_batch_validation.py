"""Regression coverage for bounded cohort-ingest identity validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data import cohort_research_database as cohort_database
from hypervector.data.research_database import ResearchDatabase


def test_insert_targets_only_exact_event_identity_conflicts() -> None:
    """The database constraint must replace a historical scan of every event."""
    assert "INSERT INTO cohort_live_events" in cohort_database._INSERT_SQL
    assert "ON CONFLICT (event_id) DO NOTHING" in cohort_database._INSERT_SQL
    assert not hasattr(cohort_database, "_validate_new_identities")


def test_append_rejects_a_conflicting_prior_run_sequence(tmp_path: Path) -> None:
    """Removing the pre-insert scan must retain append-only identity safety."""
    root = tmp_path / "cohort"
    ledger = root / "decisions.jsonl"
    _write(ledger, [_event({"state": "first"})])
    database = ResearchDatabase(tmp_path / "market.duckdb")
    database.ingest_cohort_live_ledger(root)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_event({"state": "conflict"})) + "\n")

    with pytest.raises(ValueError, match="conflicting cohort run sequence"):
        database.ingest_cohort_live_ledger(root)

    assert database.cohort_live_summary()["events"] == 1


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _event(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": 1,
        "event_type": "heartbeat",
        "observed_at_utc": "2026-09-01T08:00:00+00:00",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "cohort-v64",
        "profile_fingerprint": "a" * 64,
        "run_fingerprint": "b" * 64,
        "run_id": "run-current",
        "payload": payload,
    }
