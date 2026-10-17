"""Identity and malformed-evidence boundaries for headless attachments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.cohort_monitor_identity import (
    LedgerIdentityReader,
    active_ledger_identity,
    checkpoint_identity,
    fresh_checkpoint_document,
)
from test_cohort_monitor_stale_attachment import _checkpoint, _config, _write_ledger


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        {"mode": "multi_asset_bidirectional_live_checkpoint"},
        {"mode": "multi_asset_bidirectional_live_checkpoint", "audit": {}},
    ],
)
def test_incomplete_checkpoint_cannot_establish_identity(document: object) -> None:
    """Missing typed envelopes fail before any monitor can attach."""
    with pytest.raises(ValueError):
        checkpoint_identity(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", ""),
        ("profile_id", None),
        ("profile_fingerprint", 1),
        ("execution_mode", "paper"),
        ("live_armed", False),
    ],
)
def test_invalid_ledger_identity_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    """An identity must prove the exact armed run rather than resemble one."""
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger)
    record = json.loads(ledger.read_text())
    record[field] = value
    ledger.write_text(json.dumps(record) + "\n")
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    with pytest.raises(ValueError):
        active_ledger_identity(config)


@pytest.mark.parametrize("content", ["bad", "[]", "{}"])
def test_unreadable_checkpoint_fails_explicitly(tmp_path: Path, content: str) -> None:
    """Malformed recent bytes do not become a fresh successful attachment."""
    ledger = tmp_path / "ledger.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    checkpoint.write_text(content)
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    with pytest.raises(ValueError):
        fresh_checkpoint_document(checkpoint, config, maximum_age_seconds=90)


def test_incremental_identity_waits_for_a_complete_append(tmp_path: Path) -> None:
    """Incomplete writes preserve the validated run until their newline arrives."""
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger)
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    record = json.loads(ledger.read_text())
    record["run_id"] = "new-run"
    reader = LedgerIdentityReader(config)
    assert reader.read().run_id == "active-run"
    with ledger.open("a") as stream:
        stream.write(json.dumps(record))
    assert reader.read().run_id == "active-run"
    with ledger.open("a") as stream:
        stream.write("\n")
    assert reader.read().run_id == "new-run"


def test_incremental_monitor_refuses_identityless_ledger(tmp_path: Path) -> None:
    """A valid file with no armed identity cannot create an attachment."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"event_type":"telemetry"}\n')
    reader = LedgerIdentityReader(
        _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    )
    with pytest.raises(ValueError, match="no configuration identity"):
        reader.read()


def test_fresh_checkpoint_rejects_a_foreign_run(tmp_path: Path) -> None:
    """Recent modification time cannot substitute for exact run identity."""
    ledger = tmp_path / "ledger.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    document = _checkpoint("staged-fingerprint")
    document["audit"]["run"]["run_id"] = "foreign"
    checkpoint.write_text(json.dumps(document))
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    with pytest.raises(ValueError, match="run identity"):
        fresh_checkpoint_document(checkpoint, config, maximum_age_seconds=90)
