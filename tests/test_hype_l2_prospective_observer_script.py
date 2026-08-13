"""Tests for the standalone HYPE L2 prospective observer sidecar."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

from pytest import CaptureFixture

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE

SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_l2_prospective_observer.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hype_l2_prospective_observer_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Archive:
    def __init__(self, events: tuple[L2SnapshotEvent, ...]) -> None:
        self.events = events

    def replay_window(self, start: datetime, end: datetime) -> tuple[object, ...]:
        assert start < end
        return self.events


class _Observer:
    def __init__(self) -> None:
        self.timestamps: list[int] = []

    def observe(self, event: L2SnapshotEvent) -> tuple[dict[str, object], ...]:
        self.timestamps.append(event.exchange_ts_ms)
        if len(self.timestamps) == 1:
            return (
                {
                    "status": "scored",
                    "decision_time_ms": event.exchange_ts_ms,
                    "training_score_percentile": 0.9,
                    "predicted_gross_return_bps": 20.0,
                    "execution_authority": "none",
                },
            )
        return ()

    def warm(self, event: L2SnapshotEvent) -> None:
        self.timestamps.append(event.exchange_ts_ms)


def test_bounded_sidecar_replays_each_book_once_and_reports_no_authority(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    module = _load_module()
    observer = _Observer()
    event = _book(1_000)
    config = module.ObserverConfig(
        data_root=tmp_path,
        journal=tmp_path / "observations.jsonl",
        cohort_checkpoint=tmp_path / "checkpoint.json",
        status=tmp_path / "status.json",
        poll_seconds=1.0,
        lookback_seconds=180,
        max_polls=1,
    )

    result = module.run_observer(
        config,
        observer=observer,
        archive=_Archive((event,)),
        clock=lambda: datetime(2026, 8, 6, tzinfo=UTC),
        sleeper=lambda _seconds: None,
    )

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert result == 0
    assert observer.timestamps == [1_000]
    assert rows[0]["execution_authority"] == "none"
    assert rows[-1]["event_type"] == "hype_l2_observer_stopped"
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "stopped"
    assert status["execution_authority"] == "none"
    assert status["latest_observation"]["status"] == "scored"


def _book(timestamp_ms: int) -> L2SnapshotEvent:
    bid = BookLevel(50.0, 2.0, 1)
    ask = BookLevel(50.1, 2.0, 1)
    return L2SnapshotEvent(
        "HYPE",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        (bid,),
        (ask,),
        source=REST_L2_SOURCE,
    )
