"""Authenticity and bounded-read checks for recovered cohort identities."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from hypervector.research import live_ledger_snapshot as snapshots
from test_multi_asset_live_audit import _cohort_rows


def test_identity_cache_reuses_authenticated_offsets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warm publication reads exact identity rows without another reverse scan."""
    path, offset = _ledger(tmp_path)
    rows, evidence = snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )

    def refuse_scan(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("warm ancestry rescanned history")

    monkeypatch.setattr(snapshots, "_reverse_complete_lines", refuse_scan)
    repeated, verified = snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )
    assert repeated == rows
    assert verified == evidence
    assert rows[0]["run_id"] == "prior"
    assert evidence[0]["source_offset"] == 0
    assert len(evidence[0]["sha256"]) == 64


@pytest.mark.parametrize("mutation", ["rewrite", "truncate", "replace"])
def test_cached_identity_rejects_changed_source(tmp_path: Path, mutation: str) -> None:
    """Stale cached provenance cannot survive rewriting or replacement of its file."""
    path, offset = _ledger(tmp_path)
    snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )
    original = path.read_bytes()
    if mutation == "rewrite":
        path.write_bytes(
            original.replace(
                b"cohort-profile-fingerprint", b"changed-profile-fingerpri", 1
            )
        )
    elif mutation == "truncate":
        path.write_bytes(original[:offset])
    else:
        replacement = tmp_path / "replacement.jsonl"
        replacement.write_bytes(original)
        os.replace(replacement, path)
    with pytest.raises(ValueError, match="changed|truncated"):
        snapshots.configuration_identity_ancestry(
            path, frozenset({"prior"}), before_offset=offset
        )


def test_ancestry_cannot_use_current_or_future_identity(tmp_path: Path) -> None:
    """Requested history is bound strictly before the selected current-run prefix."""
    path, offset = _ledger(tmp_path)
    snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )
    with pytest.raises(ValueError, match="not prior"):
        snapshots.configuration_identity_ancestry(
            path, frozenset({"prior"}), before_offset=0
        )


def test_missing_ancestral_identity_is_an_explicit_error(tmp_path: Path) -> None:
    """Absence of provenance is not converted into a successful empty history."""
    path, offset = _ledger(tmp_path)
    with pytest.raises(ValueError, match="configuration identities missing"):
        snapshots.configuration_identity_ancestry(
            path, frozenset({"unknown-run"}), before_offset=offset
        )


def _ledger(tmp_path: Path) -> tuple[Path, int]:
    """Create a prior identity and a separately identified current cohort suffix."""
    current = _cohort_rows()
    prior = deepcopy(current[0])
    prior["run_id"] = "prior"
    encoded = json.dumps(prior) + "\n"
    suffix = "".join(
        json.dumps({**row, "sequence": index}) + "\n"
        for index, row in enumerate(current, 2)
    )
    path = tmp_path / "decisions.jsonl"
    path.write_text(encoded + suffix)
    return path, len(encoded.encode())


def test_recovered_entry_requires_an_authenticated_prior_prefix(tmp_path: Path) -> None:
    """An entry from another run cannot acquire invented cohort provenance."""
    from cohort_live_audit_trade_fixture import traded_asset_rows
    from hypervector.research.cohort_checkpoint_asset_snapshots import (
        recover_cohort_execution_identities,
    )

    with pytest.raises(ValueError, match="prior cohort identity prefix"):
        recover_cohort_execution_identities(
            tmp_path / "absent.jsonl",
            _cohort_rows(),
            {"source_start_offset": 0},
            {"BTC": traded_asset_rows("prior")},
        )


def test_cached_ancestry_remembers_largest_verified_source(tmp_path: Path) -> None:
    """Truncation after a successful warm read must not escape cache validation."""
    path, offset = _ledger(tmp_path)
    original = path.read_bytes()
    snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )
    path.write_bytes(original + b"\n\n")
    snapshots.configuration_identity_ancestry(
        path, frozenset({"prior"}), before_offset=offset
    )
    path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="truncated"):
        snapshots.configuration_identity_ancestry(
            path, frozenset({"prior"}), before_offset=offset
        )


@pytest.mark.parametrize("sequence", [True, 0, "1"])
def test_ancestry_rejects_invalid_source_sequence(
    tmp_path: Path, sequence: object
) -> None:
    """Rebasing cannot conceal malformed sequence metadata in a recovered identity."""
    path, offset = _ledger(tmp_path)
    original = path.read_bytes()
    boundary, suffix = original[:offset], original[offset:]
    row = json.loads(boundary)
    row["sequence"] = sequence
    changed = (json.dumps(row) + "\n").encode()
    path.write_bytes(changed + suffix)
    with pytest.raises(ValueError, match="ancestry.*sequence"):
        snapshots.configuration_identity_ancestry(
            path, frozenset({"prior"}), before_offset=len(changed)
        )
