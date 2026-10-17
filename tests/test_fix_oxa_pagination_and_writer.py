"""Regression: one pagination helper with a consistent cursor guard, faster pages.

Books, trades and candles used to re-request a stuck vendor cursor until
``max_pages`` (up to 500 calls for backfill trades) and repeated book pages
were silently counted as ``coalesced_same_ms``. All five data families now
share one guarded loop and one raw-page writer.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hypervector.data import (
    oxa_candles,
    oxa_history,
    oxa_liquidations,
    oxa_prices,
    oxa_trades,
)
from hypervector.data.oxa_pagination import paginate, write_raw_pages
from hypervector.data.oxa_storage import write_gzip_json


@dataclass(frozen=True)
class Page:
    next_cursor: str | None
    raw_payload: object = None


def test_paginate_stops_at_null_cursor() -> None:
    cursors = iter(["a", "b", None])
    requested: list[str | None] = []

    def fetch(cursor: str | None) -> Page:
        requested.append(cursor)
        return Page(next(cursors))

    pages, cursor = paginate(fetch, 10, label="test")

    assert len(pages) == 3
    assert cursor is None
    assert requested == [None, "a", "b"]


def test_paginate_reports_unfinished_cursor_at_budget() -> None:
    pages, cursor = paginate(lambda c: Page(f"{c or ''}x"), 3, label="test")

    assert len(pages) == 3
    assert cursor == "xxx"


@pytest.mark.parametrize("sequence", [["same", "same"], ["a", "b", "a"]])
def test_paginate_rejects_repeated_cursor(sequence: list[str]) -> None:
    cursors = iter(sequence)
    calls = 0

    def fetch(_cursor: str | None) -> Page:
        nonlocal calls
        calls += 1
        return Page(next(cursors))

    with pytest.raises(ValueError, match="0xArchive test cursor did not advance"):
        paginate(fetch, 500, label="test")
    assert calls == len(sequence)


START = datetime(2026, 7, 26, 23, tzinfo=UTC)
END = datetime(2026, 7, 27, 0, tzinfo=UTC)


@dataclass
class Reply:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload


class StuckSession:
    """Always return the same page and the same continuation cursor."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        self.calls = 0

    def get(self, url: str, **_kwargs: object) -> Reply:
        self.calls += 1
        return Reply(
            {
                "success": True,
                "data": [self.row],
                "meta": {"request_id": f"r-{self.calls}", "next_cursor": "stuck"},
            }
        )


BOOK_ROW = {
    "symbol": "BTC",
    "timestamp": "2026-07-26T23:10:00Z",
    "bids": [{"px": "65370.0", "sz": "1.0", "n": 1}],
    "asks": [{"px": "65371.0", "sz": "1.0", "n": 1}],
}
TRADE_ROW = {
    "symbol": "BTC",
    "price": "65370",
    "size": "0.1",
    "timestamp": "2026-07-26T23:10:00Z",
    "trade_id": 1,
    "side": "A",
    "crossed": True,
}
CANDLE_ROW = {
    "timestamp": "2026-07-26T23:10:00Z",
    "open": 100.0,
    "high": 101.0,
    "low": 99.0,
    "close": 100.5,
    "volume": 2.0,
    "quote_volume": 201.0,
    "trade_count": 3,
}
PRICE_ROW = {
    "timestamp": "2026-07-26T23:10:00Z",
    "mark_price": "1",
    "oracle_price": "1",
    "mid_price": "1",
}
LIQUIDATION_ROW = {
    "symbol": "BTC",
    "timestamp": "2026-07-26T23:10:00Z",
    "liquidated_user": "0x" + "1" * 40,
    "price": "77800.5",
    "size": "0.75",
    "side": "B",
    "direction": "Close Short",
    "trade_id": 9,
}


@pytest.mark.parametrize(
    ("label", "row", "fetch"),
    [
        (
            "book",
            BOOK_ROW,
            lambda session: oxa_history.fetch_orderbook_history(
                oxa_history.OxaHistoryClient(api_key="k", session=session),
                oxa_history.OxaBookRequest("BTC", START, END, max_pages=500),
            ),
        ),
        (
            "trade",
            TRADE_ROW,
            lambda session: oxa_trades.fetch_trade_history(
                oxa_trades.OxaTradeClient(api_key="k", session=session),
                oxa_trades.OxaTradeRequest("BTC", START, END, max_pages=500),
            ),
        ),
        (
            "candle",
            CANDLE_ROW,
            lambda session: oxa_candles.fetch_candle_history(
                oxa_candles.OxaCandleClient(api_key="k", session=session),
                oxa_candles.OxaCandleRequest("BTC", START, END, "1m", 10_000, 500),
            ),
        ),
        (
            "price",
            PRICE_ROW,
            lambda session: oxa_prices.fetch_price_history(
                oxa_prices.OxaPriceClient(api_key="k", session=session),
                oxa_prices.OxaPriceRequest("BTC", START, END, max_pages=500),
            ),
        ),
        (
            "liquidation",
            LIQUIDATION_ROW,
            lambda session: oxa_liquidations.fetch_liquidation_history(
                oxa_liquidations.OxaLiquidationClient(api_key="k", session=session),
                oxa_liquidations.OxaLiquidationRequest(
                    "BTC", START, END, max_pages=500
                ),
            ),
        ),
    ],
)
def test_every_family_rejects_a_stuck_cursor_after_two_calls(
    label: str, row: dict[str, Any], fetch: Any
) -> None:
    session = StuckSession(row)

    with pytest.raises(ValueError, match=f"0xArchive {label} cursor did not advance"):
        fetch(session)

    assert session.calls == 2


@pytest.mark.parametrize(
    "module", [oxa_history, oxa_trades, oxa_candles, oxa_prices, oxa_liquidations]
)
def test_families_share_one_raw_page_writer(module: Any) -> None:
    assert not hasattr(module, "_write_raw_pages")


def test_raw_pages_are_compact_level_six_deterministic_and_round_trip(
    tmp_path: Path,
) -> None:
    payload = {"success": True, "data": [{"px": "1.5", "n": 2}], "meta": {"z": None}}
    pages = [Page(None, payload), Page(None, {"b": 1, "a": [1, 2]})]
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()

    evidence = write_raw_pages(first, pages)
    assert write_raw_pages(second, pages) == evidence

    assert sorted(evidence) == ["raw/page-0001.json.gz", "raw/page-0002.json.gz"]
    raw = (first / "page-0001.json.gz").read_bytes()
    assert raw[8] == 0  # gzip XFL: neither max (9) nor fastest (1) compression
    text = gzip.decompress(raw).decode("utf-8")
    assert text == json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    assert json.loads(text) == payload


def test_write_gzip_json_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "page.json.gz"
    write_gzip_json(path, {"a": 1})

    with pytest.raises(FileExistsError):
        write_gzip_json(path, {"a": 2})
