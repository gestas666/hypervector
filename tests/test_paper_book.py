"""BookSnapshot, HL L2 parse, and BookFeed freshness (Phase 4a Task 2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from requests import ConnectionError

from hypervector.paper.book import (
    BookFeed,
    BookLevel,
    BookSnapshot,
    parse_hl_l2_payload,
    summarize_book,
)

FIX = Path(__file__).parent / "fixtures" / "hl_l2_sample.json"


def test_parse_hl_l2_orders_bids_desc_asks_asc():
    raw = json.loads(FIX.read_text())
    snap = parse_hl_l2_payload(raw, symbol="BTC-PERP", ts_recv_ms=1700000001000)
    assert not snap.is_empty()
    assert snap.best_bid() == 100.0
    assert snap.best_ask() == 100.1
    assert snap.bids[0].size == 1.5
    assert snap.asks[0].size == 2.0
    assert snap.symbol == "BTC-PERP"
    assert snap.ts_exchange_ms == 1700000000000
    assert snap.ts_recv_ms == 1700000001000


def test_parse_hl_l2_sequence_levels():
    raw = {
        "time": 42,
        "levels": [
            [["99.5", "2.0"], ["99.0", "1.0"]],
            [["100.0", "1.5"], ["100.5", "0.5"]],
        ],
    }
    snap = parse_hl_l2_payload(raw, symbol="ETH-PERP", ts_recv_ms=100.0)
    assert snap.best_bid() == 99.5
    assert snap.best_ask() == 100.0
    assert snap.bids[1].price == 99.0
    assert snap.asks[1].price == 100.5
    assert snap.ts_exchange_ms == 42.0


def test_parse_hl_l2_empty_levels():
    raw = {"levels": [[], []]}
    snap = parse_hl_l2_payload(raw, symbol="BTC-PERP", ts_recv_ms=1.0)
    assert snap.is_empty()
    assert snap.best_bid() is None
    assert snap.best_ask() is None
    assert snap.ts_exchange_ms is None


def test_parse_hl_l2_sorts_defensively():
    raw = {
        "levels": [
            [{"px": "99.0", "sz": "1"}, {"px": "100.0", "sz": "2"}],
            [{"px": "101.0", "sz": "1"}, {"px": "100.5", "sz": "3"}],
        ]
    }
    snap = parse_hl_l2_payload(raw, symbol="BTC-PERP", ts_recv_ms=1.0)
    assert [b.price for b in snap.bids] == [100.0, 99.0]
    assert [a.price for a in snap.asks] == [100.5, 101.0]


def test_book_age_uses_exchange_ts_when_set():
    snap = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=5000.0,
        ts_exchange_ms=1000.0,
        source="fixture",
    )
    assert snap.age_ms(3000.0) == 2000.0


def test_book_age_falls_back_to_recv_ts():
    snap = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=1000.0,
        ts_exchange_ms=None,
        source="fixture",
    )
    assert snap.age_ms(2500.0) == 1500.0


def test_book_age_and_freshness():
    snap = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=1000.0,
        ts_exchange_ms=1000.0,
        source="fixture",
    )
    feed = BookFeed("BTC-PERP", max_age_ms=3000)
    feed.update(snap)
    assert feed.latest() is snap
    assert feed.is_fresh(now_ms=2000.0) is True
    assert feed.is_fresh(now_ms=5000.0) is False


def test_book_feed_is_fresh_false_when_empty():
    feed = BookFeed("BTC-PERP", max_age_ms=3000)
    assert feed.latest() is None
    assert feed.is_fresh(now_ms=1000.0) is False


def test_book_feed_poll_updates_and_returns_snapshot():
    raw = json.loads(FIX.read_text())
    snap = parse_hl_l2_payload(raw, symbol="BTC-PERP", ts_recv_ms=1700000001000)
    feed = BookFeed("BTC-PERP", max_age_ms=3000)
    with patch(
        "hypervector.paper.book.fetch_hl_l2_book", return_value=snap
    ) as mock_fetch:
        out = feed.poll()
    mock_fetch.assert_called_once()
    assert out is snap
    assert feed.latest() is snap
    assert feed.is_fresh(now_ms=1700000002000.0) is True


def test_book_feed_poll_returns_none_on_error():
    feed = BookFeed("BTC-PERP", max_age_ms=3000)
    with patch(
        "hypervector.paper.book.fetch_hl_l2_book",
        side_effect=RuntimeError("network down"),
    ):
        out = feed.poll()
    assert out is None
    assert feed.latest() is None


def test_summarize_book_reports_measured_depth_and_pressure() -> None:
    """Backend telemetry derives microstructure only from observed L2 levels."""
    snapshot = BookSnapshot(
        symbol="BTC",
        bids=(BookLevel(100.0, 3.0), BookLevel(99.5, 1.0)),
        asks=(BookLevel(100.5, 1.0), BookLevel(101.0, 1.0)),
        ts_recv_ms=2_000.0,
        ts_exchange_ms=1_900.0,
        source="fixture",
    )

    metrics = summarize_book(snapshot, depth_levels=2)

    assert metrics.mid_price == pytest.approx(100.25)
    assert metrics.spread_bps == pytest.approx(49.87531172)
    assert metrics.bid_depth_ratio == pytest.approx(2.0)
    assert metrics.order_pressure_index == pytest.approx(1.0 / 3.0)
    assert metrics.bid_depth == pytest.approx(4.0)
    assert metrics.ask_depth == pytest.approx(2.0)


def test_fetch_hl_l2_book_posts_and_parses():
    from hypervector.data.hl import fetch_hl_l2_book

    raw = json.loads(FIX.read_text())
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = raw
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp

    with patch("hypervector.data.hl.time.time", return_value=1700000001.0):
        snap = fetch_hl_l2_book("BTC-PERP", session=mock_sess)

    mock_sess.post.assert_called_once()
    args, kwargs = mock_sess.post.call_args
    assert kwargs["json"] == {"type": "l2Book", "coin": "BTC"}
    assert snap.best_bid() == 100.0
    assert snap.best_ask() == 100.1
    assert snap.source == "hl_rest_l2"
    assert snap.ts_recv_ms == 1700000001000.0
    assert snap.symbol == "BTC-PERP"


def test_fetch_hl_l2_book_retries_transient_connection_failure():
    """One transient connection failure cannot degrade a five-second observer poll."""
    from hypervector.data.hl import fetch_hl_l2_book

    raw = json.loads(FIX.read_text())
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = raw
    mock_sess = MagicMock()
    mock_sess.post.side_effect = [ConnectionError("temporary disconnect"), mock_resp]
    delays: list[float] = []

    snap = fetch_hl_l2_book(
        "BTC-PERP",
        session=mock_sess,
        sleep_fn=delays.append,
    )

    assert mock_sess.post.call_count == 2
    assert delays == [1.0]
    assert snap.best_bid() == 100.0


def test_fetch_hl_l2_book_fails_after_bounded_connection_retries():
    """Persistent transport failure remains explicit after the retry budget."""
    from hypervector.data.hl import fetch_hl_l2_book

    mock_sess = MagicMock()
    mock_sess.post.side_effect = ConnectionError("persistent disconnect")
    delays: list[float] = []

    with pytest.raises(RuntimeError, match="HL l2Book fetch failed") as captured:
        fetch_hl_l2_book(
            "BTC-PERP",
            session=mock_sess,
            sleep_fn=delays.append,
        )

    assert mock_sess.post.call_count == 4
    assert delays == [1.0, 2.0, 4.0]
    assert isinstance(captured.value.__cause__, ConnectionError)


def test_fetch_hl_l2_book_raises_on_http_error():
    from hypervector.data.hl import fetch_hl_l2_book

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("503")
    mock_sess = MagicMock()
    mock_sess.post.return_value = mock_resp

    with pytest.raises(RuntimeError, match="HL l2Book"):
        fetch_hl_l2_book("BTC-PERP", session=mock_sess)
