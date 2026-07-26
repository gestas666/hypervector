"""Gap-aware live Hyperliquid event-recorder tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_event_stream import (
    HyperliquidEventRecorder,
    subscription_messages,
)
from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)

FIXTURES = Path("tests/fixtures")
RECEIVED_NS = 1_785_103_200_300_000_000


def payload(name: str) -> str:
    """Return one sanitized official-shape WebSocket message."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_subscribes_only_to_public_mainnet_execution_evidence() -> None:
    messages = tuple(json.loads(item) for item in subscription_messages("BTC"))

    assert messages == (
        {
            "method": "subscribe",
            "subscription": {"type": "l2Book", "coin": "BTC"},
        },
        {
            "method": "subscribe",
            "subscription": {"type": "trades", "coin": "BTC"},
        },
        {
            "method": "subscribe",
            "subscription": {"type": "activeAssetCtx", "coin": "BTC"},
        },
    )


def test_recorder_archives_and_drains_normalized_events(tmp_path: Path) -> None:
    recorder = HyperliquidEventRecorder(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
    )

    recorder.record_message(payload("hl_ws_l2_sample.json"), RECEIVED_NS)
    recorder.record_message(payload("hl_ws_trades_sample.json"), RECEIVED_NS + 1)
    recorder.record_message(
        payload("hl_ws_active_asset_ctx_sample.json"),
        RECEIVED_NS + 2,
    )
    events = recorder.drain()
    recorder.close()

    assert len(events) == 4
    assert isinstance(events[0], L2SnapshotEvent)
    assert all(isinstance(item, PublicTradeEvent) for item in events[1:3])
    assert isinstance(events[3], AssetContextEvent)
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    assert len(archive.replay_l2()) == 1
    assert len(archive.replay_trades()) == 2
    assert len(archive.replay_asset_contexts()) == 1


def test_reconnect_gap_precedes_first_new_event_and_is_archived(
    tmp_path: Path,
) -> None:
    recorder = HyperliquidEventRecorder(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
    )
    recorder.record_message(payload("hl_ws_l2_sample.json"), RECEIVED_NS)
    recorder.drain()
    recorder.declare_disconnect(
        detected_ts_ns=RECEIVED_NS + 10,
        reason="websocket_reconnect",
    )

    recorder.record_message(payload("hl_ws_trades_sample.json"), RECEIVED_NS + 20)
    gap, *trades = recorder.drain()
    recorder.close()

    assert isinstance(gap, StreamGap)
    assert gap.previous_exchange_ts_ms == 1_785_103_200_000
    assert gap.next_exchange_ts_ms == 1_785_103_200_100
    assert all(isinstance(item, PublicTradeEvent) for item in trades)
    archive = EventArchive(data_root=tmp_path, symbol="BTC", batch_size=10)
    assert archive.replay_gaps() == (gap,)


def test_duplicate_message_does_not_reenter_execution_buffer(tmp_path: Path) -> None:
    recorder = HyperliquidEventRecorder(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
    )
    message = payload("hl_ws_trades_sample.json")

    recorder.record_message(message, RECEIVED_NS)
    recorder.record_message(message, RECEIVED_NS + 1)

    assert len(recorder.drain()) == 2


def test_out_of_order_channel_message_does_not_rewind_gap_boundary(
    tmp_path: Path,
) -> None:
    recorder = HyperliquidEventRecorder(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
    )
    recorder.record_message(payload("hl_ws_l2_sample.json"), RECEIVED_NS)
    old = json.loads(payload("hl_ws_trades_sample.json"))
    for row in old["data"]:
        row["time"] = 1_785_103_199_000
    recorder.record_message(json.dumps(old), RECEIVED_NS + 1)
    recorder.drain()
    recorder.declare_disconnect(
        detected_ts_ns=RECEIVED_NS + 2,
        reason="websocket_reconnect",
    )
    recorder.close()

    gap = recorder.drain()[0]
    assert isinstance(gap, StreamGap)
    assert gap.previous_exchange_ts_ms == 1_785_103_200_000


def test_malformed_message_fails_without_success_shaped_event(tmp_path: Path) -> None:
    recorder = HyperliquidEventRecorder(
        data_root=tmp_path,
        symbol="BTC",
        archive_batch_size=10,
    )

    with pytest.raises(ValueError, match="JSON object"):
        recorder.record_message("[]", RECEIVED_NS)

    assert recorder.drain() == ()
