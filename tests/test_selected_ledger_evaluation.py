"""Tests for bounded exact-event evidence from append-only ledgers."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _module() -> object:
    try:
        return importlib.import_module(
            "hypervector.research.selected_ledger_evaluation"
        )
    except ModuleNotFoundError:
        pytest.fail("selected ledger evaluation reader is not implemented")


def _row(sequence: int, decision_time_ms: int) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "sequence": sequence,
        "run_id": "run-1",
        "payload": {
            "evaluations": [
                {
                    "strategy_id": "provider-v1",
                    "symbol": "HYPE",
                    "decision_time_ms": decision_time_ms,
                    "eligible": False,
                }
            ]
        },
    }


def _write(path: Path, rows: list[dict[str, object]], tail: bytes = b"") -> None:
    raw = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows
    )
    path.write_bytes(raw + tail)


def test_reader_selects_one_complete_event_and_records_tail(tmp_path: Path) -> None:
    """The reader must bind one exact completed row without loading the ledger."""
    path = tmp_path / "decisions.jsonl"
    _write(path, [_row(1, 120_000), _row(2, 123_000)], b'{"partial":')

    selected = _module().read_exact_provider_evaluation(
        path,
        run_id="run-1",
        provider_id="provider-v1",
        symbol="HYPE",
        decision_time_ms=123_000,
    )

    assert selected.row["sequence"] == 2
    assert selected.evidence["incomplete_tail_dropped"] is True
    assert selected.evidence["event_sha256"]
    _module().require_selected_evaluation_unchanged(selected)


def test_reader_rejects_duplicate_exact_events(tmp_path: Path) -> None:
    """Duplicate target rows make the point-in-time identity ambiguous."""
    path = tmp_path / "decisions.jsonl"
    _write(path, [_row(1, 123_000), _row(2, 123_000)])

    with pytest.raises(ValueError, match="duplicate exact provider evaluation"):
        _module().read_exact_provider_evaluation(
            path,
            run_id="run-1",
            provider_id="provider-v1",
            symbol="HYPE",
            decision_time_ms=123_000,
        )


def test_revalidation_rejects_selected_event_mutation(tmp_path: Path) -> None:
    """Publication must fail when the selected source row changes."""
    path = tmp_path / "decisions.jsonl"
    _write(path, [_row(1, 123_000)])
    selected = _module().read_exact_provider_evaluation(
        path,
        run_id="run-1",
        provider_id="provider-v1",
        symbol="HYPE",
        decision_time_ms=123_000,
    )
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"eligible":false', b'"eligible":true '))

    with pytest.raises(RuntimeError, match="selected ledger event changed"):
        _module().require_selected_evaluation_unchanged(selected)
