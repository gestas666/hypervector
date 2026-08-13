"""Append-only history contracts for continuous cohort improvement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.cohort_improvement_history import append_material_report


def test_history_appends_only_distinct_material_states(tmp_path: Path) -> None:
    """Polling the same hypothesis state must not spam the durable ledger."""
    path = tmp_path / "history.jsonl"
    report = _report("a" * 64)

    assert append_material_report(path, report) is True
    assert append_material_report(path, report) is False
    assert append_material_report(path, _report("b" * 64)) is True

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[0]["previous_event_sha256"] is None
    assert rows[1]["previous_event_sha256"] == rows[0]["event_sha256"]
    assert rows[1]["material_state_sha256"] == "b" * 64


def test_history_rejects_a_corrupt_existing_chain(tmp_path: Path) -> None:
    """A broken audit trail must fail closed instead of being overwritten."""
    path = tmp_path / "history.jsonl"
    path.write_text('{"sequence":1,"event_sha256":"bad"}\n')

    with pytest.raises(ValueError, match="history event"):
        append_material_report(path, _report("c" * 64))


def _report(material_hash: str) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-13T22:00:00+00:00",
        "material_state_sha256": material_hash,
        "source": {
            "run_id": "run-51",
            "profile_id": "profile-51",
            "profile_fingerprint": "d" * 64,
        },
        "operational_assessment": {"status": "healthy"},
        "highest_value_next_investigation": {"route": "range|SOL"},
        "hypothesis_ledger": [{"route": "range|SOL", "status": "being_tested"}],
        "change_proposals": [],
        "contract": {"report_only": True, "execution_authority": "none"},
    }
