"""Read-only Hyperliquid market-event recorder command tests."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

from pytest import CaptureFixture, raises

from hypervector.data.hl_event_stream import RecordedEvent
from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "hyperliquid_event_recorder.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hyperliquid_event_recorder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Pump:
    """Deterministic event pump with no order-execution surface."""

    def __init__(self, events: tuple[RecordedEvent, ...]) -> None:
        self.events = events
        self.started = False
        self.closed = False
        self.flushes = 0

    def start(self) -> None:
        self.started = True

    def pump(self, consumer: object) -> int:
        delivered = 0
        for event in self.events:
            getattr(consumer, "ingest_hyperliquid_event")(event)
            delivered += 1
        self.events = ()
        return delivered

    def close(self) -> None:
        self.closed = True

    def flush(self) -> None:
        self.flushes += 1


def _events() -> tuple[RecordedEvent, ...]:
    level = BookLevel(price=63_000.0, size=1.0, order_count=1)
    return (
        L2SnapshotEvent("BTC", 1_000, 1_000_000_000, (level,), (level,)),
        PublicTradeEvent(
            "BTC",
            "buy",
            63_000.0,
            0.1,
            "0x1",
            1_001,
            1_001_000_000,
            7,
            "buyer",
            "seller",
        ),
        AssetContextEvent(
            "BTC",
            1_002,
            1_002_000_000,
            63_000.0,
            63_001.0,
            0.00001,
            10_000.0,
            63_000.5,
        ),
        StreamGap(
            "BTC",
            "l2Book,trades,activeAssetCtx",
            1_003_000_000,
            "test",
            1_000,
            1_001,
        ),
    )


def test_archive_only_consumer_counts_all_evidence_types() -> None:
    module = _load_module()
    consumer = module.ArchiveOnlyConsumer(symbol="BTC")

    for event in _events():
        consumer.ingest_hyperliquid_event(event)

    assert consumer.snapshot() == {
        "l2_snapshots": 1,
        "public_trades": 1,
        "asset_contexts": 1,
        "stream_gaps": 1,
        "total_events": 4,
    }


def test_run_recorder_is_bounded_read_only_and_closes_pump(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    module = _load_module()
    pump = _Pump(_events())
    config = module.RecorderConfig(
        symbol="BTC",
        data_root=tmp_path,
        archive_batch_size=100,
        poll_seconds=0.01,
        status_seconds=60.0,
        max_polls=1,
    )

    result = module.run_recorder(
        config,
        pump=pump,
        sleeper=lambda _seconds: None,
    )

    assert result == 0
    assert pump.started and pump.closed
    output = capsys.readouterr().out
    rows = tuple(json.loads(line) for line in output.splitlines())
    assert rows[0]["event_type"] == "market_event_recorder_started"
    assert rows[0]["execution_authority"] == "none"
    assert rows[0]["channels"] == ["l2Book", "trades", "activeAssetCtx"]
    assert rows[-1]["event_type"] == "market_event_recorder_stopped"
    assert rows[-1]["counts"]["public_trades"] == 1


def test_run_recorder_flushes_live_tail_on_a_bounded_interval(
    tmp_path: Path,
) -> None:
    module = _load_module()
    pump = _Pump(_events())
    clock = iter((0.0, 0.0, 31.0))
    config = module.RecorderConfig(
        symbol="BTC",
        data_root=tmp_path,
        archive_batch_size=2_000,
        poll_seconds=0.01,
        status_seconds=60.0,
        flush_seconds=30.0,
        max_polls=1,
    )

    module.run_recorder(
        config,
        pump=pump,
        sleeper=lambda _seconds: None,
        monotonic=lambda: next(clock),
    )

    assert pump.flushes == 1
    assert pump.closed is True


def test_config_preserves_exact_hip3_identity_and_archive_path() -> None:
    module = _load_module()

    args = module.build_parser().parse_args(["--symbol", "xyz:skhx"])
    config = module.config_from_args(args)

    assert config.symbol == "xyz:SKHX"
    assert config.archive_path == Path("data/cache/events/hyperliquid/xyz:SKHX")


def test_direct_config_rejects_noncanonical_hip3_identity() -> None:
    module = _load_module()

    with raises(ValueError, match="HIP-3 symbol"):
        module.RecorderConfig(symbol="XYZ:SKHX", data_root=Path("data"))
