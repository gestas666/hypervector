"""Append-only source-long forward-monitor tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
)
from hypervector.research.source_long_forward_monitor import (
    SourceLongForwardMonitor,
    SourceLongOutcomeLedger,
    discover_source_long_candidates,
)

_START = datetime(2026, 7, 31, 13, 20, tzinfo=UTC)
_START_MS = int(_START.timestamp() * 1_000)


class _Archive:
    def __init__(self, events: tuple[RecordedEvent, ...]) -> None:
        self.events = events
        self.calls = 0

    def replay_window(
        self,
        _start: datetime,
        _end: datetime,
    ) -> tuple[RecordedEvent, ...]:
        self.calls += 1
        return self.events


def _write_backend_ledger(path: Path) -> None:
    rows = (
        {
            "event_type": "reconciliation",
            "observed_at_utc": (_START - timedelta(seconds=1)).isoformat(),
            "run_id": "run-1",
            "payload": {"account_value_usd": 153.61},
        },
        {
            "event_type": "regime_decision",
            "observed_at_utc": _START.isoformat(),
            "run_id": "run-1",
            "payload": {
                "label_time_utc": (_START - timedelta(minutes=5)).isoformat(),
                "available_at_utc": _START.isoformat(),
                "source_long_observer": {
                    "recipe_id": "fade_td_eu",
                    "side": "long",
                    "authority": "observe_only",
                    "maximum_hold_seconds": 86_400.0,
                },
            },
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _completed_events() -> tuple[RecordedEvent, ...]:
    bid = BookLevel(100.0, 5.0, 1)
    ask = BookLevel(101.0, 5.0, 1)

    def book(offset: int) -> L2SnapshotEvent:
        timestamp = _START_MS + offset
        return L2SnapshotEvent("BTC", timestamp, timestamp * 1_000_000, (bid,), (ask,))

    def trade(
        offset: int,
        trade_id: int,
        side: Literal["buy", "sell"],
        price: float,
    ) -> PublicTradeEvent:
        timestamp = _START_MS + offset
        return PublicTradeEvent(
            "BTC",
            side,
            price,
            100.0,
            f"0x{trade_id}",
            timestamp,
            timestamp * 1_000_000,
            trade_id,
            "buyer",
            "seller",
        )

    return (
        book(0),
        book(100),
        trade(101, 1, "sell", 99.0),
        book(200),
        trade(201, 2, "buy", 102.0),
    )


def test_discovers_exact_observer_and_signal_time_account_equity(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "decisions.jsonl"
    _write_backend_ledger(backend)

    candidates = discover_source_long_candidates(backend)

    assert len(candidates) == 1
    assert candidates[0].spec.recipe_id == "fade_td_eu"
    assert candidates[0].spec.signal_time_utc == _START.isoformat()
    assert candidates[0].initial_equity_usd == 153.61
    assert candidates[0].source_run_id == "run-1"


def test_discovery_retries_only_an_unterminated_trailing_append(tmp_path: Path) -> None:
    backend = tmp_path / "decisions.jsonl"
    _write_backend_ledger(backend)
    with backend.open("a", encoding="utf-8") as handle:
        handle.write('{"event_type":"regime_decision"')

    candidates = discover_source_long_candidates(backend)

    assert len(candidates) == 1


def test_monitor_appends_one_resolved_outcome_without_duplicate_rows(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "decisions.jsonl"
    output = tmp_path / "long-outcomes.jsonl"
    _write_backend_ledger(backend)
    archive = _Archive(_completed_events())
    ledger = SourceLongOutcomeLedger(output)
    monitor = SourceLongForwardMonitor(
        backend_ledger=backend,
        archive=archive,
        outcome_ledger=ledger,
        base_config=SourcePortfolioReplayConfig(
            initial_equity=150.0,
            margin_fraction=0.35,
            leverage=30.0,
            target_price_fraction=1.0 / 101.0,
            receipt_timestamp_source="recorded",
        ),
    )

    first = monitor.poll(_START + timedelta(seconds=1))
    second = monitor.poll(_START + timedelta(seconds=2))

    assert len(first) == 1
    assert first[0]["payload"]["status"] == "target_completed"
    assert first[0]["execution_authority"] == "none"
    assert second == ()
    assert archive.calls == 1
    rows = tuple(json.loads(line) for line in output.read_text().splitlines())
    assert len(rows) == 1
