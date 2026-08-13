"""Tests for the public high-cadence Hyperliquid REST L2 recorder."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.data.hl_events import L2SnapshotEvent, StreamGap
from hypervector.data.hl_rest_l2_recorder import HyperliquidRestL2Recorder


@dataclass
class _Info:
    payloads: list[dict[str, object]]

    def l2_snapshot(self, name: str) -> object:
        assert name == "HYPE"
        return self.payloads.pop(0)


class _Archive:
    def __init__(self) -> None:
        self.events: list[L2SnapshotEvent] = []
        self.gaps: list[StreamGap] = []
        self.flushes = 0

    def append(self, events: tuple[L2SnapshotEvent, ...]) -> None:
        self.events.extend(events)

    def record_gap(self, gap: StreamGap) -> None:
        self.gaps.append(gap)

    def flush(self) -> None:
        self.flushes += 1


def test_recorder_preserves_exchange_time_depth_and_rest_source() -> None:
    """One public response becomes one exact, source-labeled book event."""
    archive = _Archive()
    recorder = HyperliquidRestL2Recorder(
        info=_Info([_book(1_785_103_200_000)]),
        archive=archive,
        symbol="HYPE",
        clock_ns=lambda: 1_785_103_200_300_000_000,
    )

    event = recorder.poll()

    assert event.exchange_ts_ms == 1_785_103_200_000
    assert event.received_ts_ns == 1_785_103_200_300_000_000
    assert event.source == "hyperliquid_rest_l2Book_1s"
    assert event.bids[0].price == 50.0
    assert archive.events == [event]


def test_recorder_materializes_a_transport_gap_on_recovery() -> None:
    """A failed interval remains explicit when the next book arrives."""
    archive = _Archive()
    recorder = HyperliquidRestL2Recorder(
        info=_Info([_book(1_785_103_201_000), _book(1_785_103_203_000)]),
        archive=archive,
        symbol="HYPE",
        clock_ns=lambda: 1_785_103_203_300_000_000,
    )
    recorder.poll()
    recorder.declare_gap(
        detected_ts_ns=1_785_103_202_000_000_000,
        reason="http_429",
    )

    recorder.poll()

    assert len(archive.gaps) == 1
    gap = archive.gaps[0]
    assert gap.previous_exchange_ts_ms == 1_785_103_201_000
    assert gap.next_exchange_ts_ms == 1_785_103_203_000
    assert gap.reason == "http_429"


def test_close_flushes_and_retains_an_unresolved_terminal_gap() -> None:
    """Shutdown cannot erase a final period of unknown transport coverage."""
    archive = _Archive()
    recorder = HyperliquidRestL2Recorder(
        info=_Info([]),
        archive=archive,
        symbol="HYPE",
        clock_ns=lambda: 1_785_103_203_300_000_000,
    )
    recorder.declare_gap(
        detected_ts_ns=1_785_103_202_000_000_000,
        reason="network_timeout",
    )

    recorder.close()

    assert archive.flushes == 1
    assert archive.gaps[0].next_exchange_ts_ms is None


def _book(timestamp_ms: int) -> dict[str, object]:
    return {
        "coin": "HYPE",
        "time": timestamp_ms,
        "levels": [
            [{"px": "50.0", "sz": "2.0", "n": 1}],
            [{"px": "50.1", "sz": "3.0", "n": 2}],
        ],
    }
