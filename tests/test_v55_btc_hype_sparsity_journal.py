"""Contract tests for the first v55 sparsity decision journal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_JOURNAL = _ROOT / "docs/research-journal/v55-btc-hype-sparsity-first-prefix-v1.json"


def test_v55_sparsity_journal_is_exact_and_report_only() -> None:
    """The journal must bind to v55 without granting live authority."""
    payload = json.loads(_JOURNAL.read_text())

    assert payload["runtime_identity"]["run_id"] == "bidirectional-live-1787048825207"
    assert payload["runtime_identity"]["profile_fingerprint"].startswith("e918f81e")
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["recommendation"]["proposed_live_change"] == "none"
    assert payload["highest_value_next_investigation"]["route"].endswith("xyz:SPCX")


def test_v55_sparsity_journal_reconciles_live_prefix() -> None:
    """The exact prefix cited by the decision must remain immutable."""
    payload = json.loads(_JOURNAL.read_text())
    evidence = payload["source_evidence"][0]
    source = _ROOT / evidence["path"]
    raw = source.read_bytes()

    assert len(raw) == evidence["bytes"]
    assert hashlib.sha256(raw).hexdigest() == evidence["sha256"]
    assert payload["technical_reconciliation"]["observed_routes"] == 4
    assert payload["technical_reconciliation"]["eligible_evaluations"] == 0
