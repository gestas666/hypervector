"""The native packet command can use authenticated raw recorded execution depth."""

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_book_source import FIXTURE, make_bundle
from test_native_replay_sdk import sdk

from hypervector.research.native_replay_packets import _event, _execution_source

__all__ = ["deny_external_ports"]
D = Decimal


def test_packet_execution_source_preserves_recorded_levels_and_exact_identity(
    tmp_path: Path,
) -> None:
    """The command source authenticates an original vendor snapshot rather than using candles."""
    request, directory = make_bundle(tmp_path)
    row = {
        "data_root": str(tmp_path),
        "symbol": request.symbol,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "manifest_sha256": sha256((directory / "manifest.json").read_bytes()).hexdigest(),
    }
    source = _execution_source([row], 500)
    original = json.loads(FIXTURE.read_text())
    stamp = original["normalized_row"]["ts_exchange_ms"]
    book = source(request.symbol, stamp - 500, D(".001"))
    assert book.source_id == f"0xarchive:{request.symbol}:{stamp}"
    assert [(str(r.price), str(r.quantity)) for r in book.bids] == [
        (r["px"], r["sz"]) for r in original["raw_row"]["bids"]
    ]
    assert source(request.symbol, stamp, D(".001")) == book
    with pytest.raises(ValueError, match="no declared"):
        source("BTC", stamp, D(".00001"))
    with pytest.raises(ValueError, match="overlapping"):
        _execution_source([row, row], 500)(request.symbol, stamp, D(".001"))
    with pytest.raises(ValueError, match="checksum"):
        _execution_source([{**row, "manifest_sha256": "0" * 64}], 500)(
            request.symbol, stamp, D(".001")
        )


def test_declared_price_and_funding_events_preserve_nulls_and_economic_clock() -> None:
    """Events neither replace missing midpoints with marks nor fabricate flat funding receipts."""
    replay = sdk()
    _event(
        replay,
        row={"kind": "price", "symbol": "xyz:CCC", "time_ms": 1000, "mark": "100", "mid": "100"},
    )
    replay.advance_to(1100)
    _event(
        replay,
        row={"kind": "price", "symbol": "xyz:CCC", "time_ms": 1100, "mark": "101", "mid": None},
    )
    assert not replay.mid_prices and replay.account.snapshot().mark_prices["xyz:CCC"] == 101
    _event(
        replay,
        row={
            "kind": "funding",
            "event_id": "funding:1100",
            "symbol": "xyz:CCC",
            "time_ms": 1100,
            "rate": ".001",
            "oracle_price": "102",
            "visible_delay_ms": 0,
        },
    )
    assert not replay.funding_rows
    with pytest.raises(ValueError, match="price and funding"):
        _event(replay, row={"kind": "unmodeled_liquidation"})
