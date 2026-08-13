from __future__ import annotations

import json
from pathlib import Path

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.research import range_onset_forward_observer
from hypervector.research.range_onset_event_models import EventSignal


def test_shadow_ledger_contract_is_available() -> None:
    assert hasattr(range_onset_forward_observer, "SolShadowLedger")


def _book(timestamp_ms: int) -> L2SnapshotEvent:
    return L2SnapshotEvent(
        "SOL",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        (BookLevel(99.9, 40.0, 1),),
        (BookLevel(100.1, 40.0, 1),),
    )


def test_ledger_restores_last_fsynced_state(tmp_path: Path) -> None:
    config = range_onset_forward_observer.SolShadowConfig()
    path = tmp_path / "shadow.jsonl"
    ledger = range_onset_forward_observer.SolShadowLedger(path, config)
    engine = ledger.restore_engine()
    engine.update_shared_capital(
        range_onset_forward_observer.SharedCapitalSnapshot(
            1_000,
            15_000.0,
            0.0,
            "btc-run",
        )
    )
    engine.ingest_decision(EventSignal(1_000, 100.0, True, False, False, False))
    engine.ingest_event(_book(1_100))

    ledger.append(engine.drain_records(), engine, recorded_at_ms=1_200)

    restored = range_onset_forward_observer.SolShadowLedger(
        path,
        config,
    ).restore_engine()
    assert restored.snapshot == engine.snapshot
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["sequence"] == 1
    assert rows[0]["records"][-1]["action"] == "entry_filled"
    assert rows[0]["execution_authority"] == "none"
