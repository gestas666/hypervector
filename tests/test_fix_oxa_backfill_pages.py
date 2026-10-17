"""Regression: the backfill book page bound must not abort ordinary busy hours.

Real duplicated-snapshot vendor periods filled exactly 20 book pages per hour,
so a bound of 20 aborted the whole job on the first slightly busier hour. The
bound is a named, shared default with headroom, stays configurable, and its
exhaustion error names the symbol, window, pages used and cursor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillTask,
    _acquire_task,
)
from hypervector.data.oxa_history import DEFAULT_BOOK_MAX_PAGES
from hypervector.data.oxa_prices import DEFAULT_PRICE_MAX_PAGES
from hypervector.data.oxa_trades import DEFAULT_TRADE_MAX_PAGES

START = datetime(2026, 8, 10, 2, tzinfo=UTC)
END = START + timedelta(hours=1)


@dataclass
class Reply:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload


class PagedSession:
    def __init__(self, total: int) -> None:
        self.total = total
        self.calls = 0

    def get(self, url: str, **_kwargs: object) -> Reply:
        self.calls += 1
        index = self.calls
        stamp = START + timedelta(seconds=index)
        return Reply(
            {
                "success": True,
                "data": [
                    {
                        "symbol": "BTC",
                        "timestamp": stamp.isoformat().replace("+00:00", "Z"),
                        "bids": [{"px": "65370.0", "sz": "1.0", "n": 1}],
                        "asks": [{"px": "65371.0", "sz": "1.0", "n": 1}],
                    }
                ],
                "meta": {
                    "request_id": f"book-{index}",
                    "next_cursor": None if index >= self.total else f"cur-{index}",
                },
            }
        )


def test_backfill_defaults_are_shared_named_bounds_with_headroom(
    tmp_path: Path,
) -> None:
    config = OxaBackfillConfig("BTC", START, END, tmp_path)

    assert config.book_max_pages == DEFAULT_BOOK_MAX_PAGES >= 40
    assert config.trade_max_pages == DEFAULT_TRADE_MAX_PAGES == 500
    assert config.price_max_pages == DEFAULT_PRICE_MAX_PAGES == 20


def test_twenty_one_page_book_hour_completes_with_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = PagedSession(21)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    config = OxaBackfillConfig("BTC", START, END, tmp_path, book_only=True)

    result = _acquire_task(config, OxaBackfillTask("book", START, END), "key")

    assert result.pages == 21
    assert result.rows == 21
    assert session.calls == 21


def test_exhausted_book_bound_names_symbol_window_pages_and_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = PagedSession(30)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    config = OxaBackfillConfig(
        "BTC", START, END, tmp_path, book_only=True, book_max_pages=5
    )

    with pytest.raises(ValueError, match="book max-pages exhausted") as raised:
        _acquire_task(config, OxaBackfillTask("book", START, END), "key")

    message = str(raised.value)
    assert "BTC" in message
    assert START.isoformat() in message
    assert "5 page(s)" in message
    assert "continuation_cursor='cur-5'" in message
    assert "book_max_pages" in message
    assert not any(tmp_path.rglob("manifest.json"))


def test_native_replay_reader_accepts_book_hours_the_backfill_now_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raising the writer bound must raise the authenticated reader bound too.

    The native replay execution source used a hard-coded bound of 20 pages, so a
    21-page hour the backfill now completes would be refused as exceeding the
    reader bounds even though it is complete, verified evidence.
    """
    from decimal import Decimal

    from hypervector.data.oxa_history import OxaBookRequest, output_directory
    from hypervector.data.oxa_storage import file_evidence
    from hypervector.research.native_replay_packets import _execution_source

    session = PagedSession(21)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    config = OxaBackfillConfig("BTC", START, END, tmp_path, book_only=True)
    assert _acquire_task(config, OxaBackfillTask("book", START, END), "key").pages == 21

    manifest = output_directory(tmp_path, OxaBookRequest("BTC", START, END)) / (
        "manifest.json"
    )
    execution = _execution_source(
        [
            {
                "symbol": "BTC",
                "start": START.isoformat(),
                "end": END.isoformat(),
                "data_root": str(tmp_path),
                "manifest_sha256": file_evidence(manifest)["sha256"],
            }
        ],
        1_000,
    )
    arrival_ms = int((START + timedelta(seconds=21)).timestamp() * 1000)

    book = execution("BTC", arrival_ms, Decimal("0.00001"))

    assert book.exchange_time_ms == arrival_ms
