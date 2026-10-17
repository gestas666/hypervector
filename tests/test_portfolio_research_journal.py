"""Tests for the append-only portfolio research decision journal."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.data.research_database import ResearchDatabase


def test_first_revision_is_idempotent_and_queryable(tmp_path: Path) -> None:
    """An exact research revision is appended once and remains queryable."""
    evidence = _evidence_file(tmp_path, "hype-evidence.json", {"closed": 6})
    record = _record_file(tmp_path, _record(evidence=evidence))
    database = ResearchDatabase(tmp_path / "market.duckdb")

    first = database.append_portfolio_research_revision(record)
    repeated = database.append_portfolio_research_revision(record)
    history = database.portfolio_research_history("hype-breakout-core")

    assert first.inserted is True
    assert repeated.inserted is False
    assert repeated.revision_id == first.revision_id
    assert history["execution_authority"] == "none"
    assert history["automatic_promotion"] is False
    assert history["runtime_strategy_changed"] is False
    assert history["evidence_integrity"] == {
        "changed": 0,
        "matching": 1,
        "missing": 0,
    }
    assert history["revisions"][0]["revision_id"] == first.revision_id
    assert history["revisions"][0]["status"] == "retain"
    assert database.portfolio_research_summary() == {
        "current_hypotheses": 1,
        "evidence_references": 1,
        "hypotheses": 1,
        "revisions": 1,
    }


def test_same_hypothesis_revision_rejects_changed_content(tmp_path: Path) -> None:
    """A revision number cannot be silently reused for a different decision."""
    evidence = _evidence_file(tmp_path, "evidence.json", {"pf": 1.2})
    first = _record_file(tmp_path, _record(evidence=evidence), "first.json")
    changed_payload = _record(evidence=evidence)
    changed_payload["decision"] = "Replace the active strategy."
    changed = _record_file(tmp_path, changed_payload, "changed.json")
    database = ResearchDatabase(tmp_path / "market.duckdb")
    database.append_portfolio_research_revision(first)

    with pytest.raises(ValueError, match="revision identity conflict"):
        database.append_portfolio_research_revision(changed)

    assert database.portfolio_research_summary()["revisions"] == 1


def test_revision_chain_requires_exact_prior_identity(tmp_path: Path) -> None:
    """A later revision must explicitly supersede the prior exact revision."""
    evidence = _evidence_file(tmp_path, "evidence.json", {"trades": 20})
    database = ResearchDatabase(tmp_path / "market.duckdb")
    first_path = _record_file(tmp_path, _record(evidence=evidence), "v1.json")
    first = database.append_portfolio_research_revision(first_path)
    second_payload = _record(
        evidence=evidence,
        revision_number=2,
        supersedes_revision_id=first.revision_id,
        created_at=datetime(2026, 8, 6, tzinfo=UTC),
    )
    second_payload["status"] = "candidate"
    second = database.append_portfolio_research_revision(
        _record_file(tmp_path, second_payload, "v2.json")
    )

    assert second.inserted is True
    history = database.portfolio_research_history("hype-breakout-core")
    assert [row["revision_number"] for row in history["revisions"]] == [1, 2]
    assert history["current_revision_id"] == second.revision_id

    invalid = _record(
        evidence=evidence,
        revision_number=3,
        supersedes_revision_id=first.revision_id,
        created_at=datetime(2026, 8, 7, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="must supersede revision 2"):
        database.append_portfolio_research_revision(
            _record_file(tmp_path, invalid, "invalid-v3.json")
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("execution_authority", "hyperliquid_mainnet", "execution_authority"),
        ("automatic_promotion", True, "automatic_promotion"),
        ("runtime_strategy_changed", True, "runtime_strategy_changed"),
    ],
)
def test_revision_cannot_gain_execution_authority(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    """Research records cannot mutate, promote, or execute a strategy."""
    evidence = _evidence_file(tmp_path, "evidence.json", {"sample": 1})
    payload = _record(evidence=evidence)
    payload[field] = value
    database = ResearchDatabase(tmp_path / "market.duckdb")

    with pytest.raises(ValueError, match=message):
        database.append_portfolio_research_revision(_record_file(tmp_path, payload))

    assert database.portfolio_research_summary()["revisions"] == 0


def test_evidence_hash_is_verified_on_append_and_report(tmp_path: Path) -> None:
    """Evidence must match at ingestion and later drift remains visible."""
    evidence = _evidence_file(tmp_path, "evidence.json", {"value": 1})
    payload = _record(evidence=evidence)
    payload["evidence"][0]["sha256"] = "0" * 64
    database = ResearchDatabase(tmp_path / "market.duckdb")

    with pytest.raises(ValueError, match="evidence SHA-256 mismatch"):
        database.append_portfolio_research_revision(
            _record_file(tmp_path, payload, "bad.json")
        )

    valid = _record_file(tmp_path, _record(evidence=evidence), "valid.json")
    database.append_portfolio_research_revision(valid)
    evidence.write_text('{"value":2}\n', encoding="utf-8")
    history = database.portfolio_research_history("hype-breakout-core")

    assert history["evidence_integrity"] == {
        "changed": 1,
        "matching": 0,
        "missing": 0,
    }
    assert history["revisions"][0]["evidence"][0]["integrity"] == "changed"


def _record(
    *,
    evidence: Path,
    revision_number: int = 1,
    supersedes_revision_id: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, object]:
    timestamp = created_at or datetime(2026, 8, 5, tzinfo=UTC)
    content = evidence.read_bytes()
    return {
        "schema_version": 1,
        "hypothesis_id": "hype-breakout-core",
        "revision_number": revision_number,
        "supersedes_revision_id": supersedes_revision_id,
        "created_at_utc": timestamp.isoformat(),
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "HYPE",
        "status": "retain",
        "hypothesis": "Fresh 5m breakout onsets may retain positive live edge.",
        "decision": "Retain the current profile while evidence accumulates.",
        "confidence": "low_medium",
        "falsifier": "After-cost PF <= 1 after 30 compatible live closes.",
        "evidence": [
            {
                "path": evidence.name,
                "role": "live_execution_summary",
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        ],
        "metrics": {"closed_trades": 6, "profit_factor": 10.3762},
        "limitations": ["Six closes are sparse and not independent."],
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _evidence_file(path: Path, name: str, payload: object) -> Path:
    target = path / name
    target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _record_file(
    path: Path,
    payload: dict[str, object],
    name: str = "revision.json",
) -> Path:
    target = path / name
    target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return target
