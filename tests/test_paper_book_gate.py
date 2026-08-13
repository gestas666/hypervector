"""Book entry gate: L2 decides whether we enter, not only fill price."""

from __future__ import annotations

from hypervector.paper.book import BookLevel, BookSnapshot
from hypervector.paper.book_gate import evaluate_book_entry


def _snap(
    bid: float = 100.0,
    ask: float = 100.05,
    bid_sz: float = 1.0,
    ask_sz: float = 1.0,
    ts: float = 1000.0,
) -> BookSnapshot:
    return BookSnapshot(
        symbol="BTC",
        bids=(BookLevel(bid, bid_sz),),
        asks=(BookLevel(ask, ask_sz),),
        ts_recv_ms=ts,
        ts_exchange_ms=ts,
        source="test",
    )


def test_allow_tight_spread_buy():
    # 5 bps spread at 100 → ask-bid=0.05
    r = evaluate_book_entry(
        _snap(100.0, 100.05),
        side="buy",
        now_ms=1000.0,
        max_spread_bps=10.0,
        min_touch_size=0.01,
        require_fresh=True,
    )
    assert r.allow is True
    assert r.metrics["spread_bps"] is not None


def test_reject_wide_spread():
    r = evaluate_book_entry(
        _snap(100.0, 101.0),  # 100 bps
        side="buy",
        now_ms=1000.0,
        max_spread_bps=5.0,
        require_fresh=True,
    )
    assert r.allow is False
    assert r.reason and "spread" in r.reason


def test_reject_missing_when_required():
    r = evaluate_book_entry(None, side="buy", now_ms=1.0, require_fresh=True)
    assert r.allow is False
    assert r.reason == "book_missing"


def test_allow_missing_when_not_required():
    r = evaluate_book_entry(None, side="buy", now_ms=1.0, require_fresh=False)
    assert r.allow is True


def test_reject_stale():
    r = evaluate_book_entry(
        _snap(ts=0.0),
        side="buy",
        now_ms=10_000.0,
        max_age_ms=3000.0,
        require_fresh=True,
    )
    assert r.allow is False
    assert r.reason and "stale" in r.reason


def test_reject_thin_touch_buy():
    r = evaluate_book_entry(
        _snap(ask_sz=0.001),
        side="buy",
        now_ms=1000.0,
        min_touch_size=0.01,
        require_fresh=True,
    )
    assert r.allow is False
    assert r.reason and "thin" in r.reason


def test_imbalance_gate_long():
    # ask-heavy → bad for long if min_imbalance > 0
    r = evaluate_book_entry(
        _snap(bid_sz=0.1, ask_sz=10.0),
        side="buy",
        now_ms=1000.0,
        min_imbalance=0.2,
        require_fresh=True,
    )
    assert r.allow is False
    assert r.reason and "imbalance" in r.reason
