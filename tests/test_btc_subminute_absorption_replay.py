"""Lifecycle tests for BTC subminute absorption replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_subminute_absorption_replay import (
    BtcAbsorptionReplayConfig,
    replay_btc_absorption_signals,
)


_START = pd.Timestamp("2026-01-01T00:00:00Z")
_START_MS = int(_START.timestamp() * 1_000)


def _signal(offset_ms: int = 0, event_id: str = "event") -> dict[str, object]:
    """Return one replay-compatible long signal."""
    available = _START + pd.Timedelta(milliseconds=offset_ms)
    return {
        "event_id": event_id,
        "arm": "sell_flow_absorption_candidate",
        "symbol": "BTC",
        "side": "long",
        "available_at_utc": available,
    }


def _levels(
    best: float, *, ask: bool, quantity: float = 100.0
) -> list[dict[str, float]]:
    """Return two strictly ordered visible-depth levels."""
    step = 0.1 if ask else -0.1
    return [
        {"px": best, "sz": quantity},
        {"px": best + step, "sz": quantity},
    ]


def _book(
    offset_ms: int,
    *,
    bid: float,
    ask: float,
    mid: float | None = None,
    quantity: float = 100.0,
) -> dict[str, object]:
    """Return one exact visible-depth book."""
    return {
        "ts_exchange_ms": _START_MS + offset_ms,
        "best_bid": bid,
        "best_ask": ask,
        "mid_price": (bid + ask) / 2.0 if mid is None else mid,
        "bids": _levels(bid, ask=False, quantity=quantity),
        "asks": _levels(ask, ask=True, quantity=quantity),
    }


def _empty_trades() -> pd.DataFrame:
    """Return an empty but schema-valid public-trade path."""
    return pd.DataFrame(columns=["trade_id", "ts_exchange_ms", "price"])


def _zero_funding() -> pd.Series:
    """Return one exact zero settlement before the test lifecycle."""
    return pd.Series([0.0], index=pd.DatetimeIndex([_START]), name="funding_rate")


def test_nominal_target_uses_next_causal_depth_and_maker_fee() -> None:
    """Entry must wait for latency and target must use the fixed resting price."""
    books = pd.DataFrame(
        [
            _book(400, bid=99.9, ask=100.0),
            _book(500, bid=100.0, ask=100.1),
            _book(60_000, bid=100.7006, ask=100.8),
        ]
    )

    report = replay_btc_absorption_signals(
        pd.DataFrame([_signal()]),
        books,
        _empty_trades(),
        _zero_funding(),
    )

    assert len(report.trades) == 1
    trade = report.trades.iloc[0]
    assert trade["entry_time_ms"] == _START_MS + 500
    assert trade["entry_price"] == pytest.approx(100.1)
    assert trade["exit_reason"] == "fixed_target"
    assert trade["exit_price"] == pytest.approx(100.1 * 1.006)
    assert trade["fee_usd"] == pytest.approx(
        trade["entry_notional_usd"] * 0.00045 + trade["exit_notional_usd"] * 0.00015
    )
    assert report.execution_authority == "none"
    assert report.orders_attempted is False


def test_public_trade_stop_wins_same_timestamp_and_exits_visible_bid() -> None:
    """A same-time stop and target ambiguity must resolve stop-first."""
    config = BtcAbsorptionReplayConfig(stop_trigger_proxy="public_trade")
    entry = _book(500, bid=100.0, ask=100.1)
    stop = 100.1 * 0.994
    target = 100.1 * 1.006
    books = pd.DataFrame(
        [entry, _book(60_000, bid=target, ask=target + 0.1, mid=target + 0.05)]
    )
    trades = pd.DataFrame(
        [{"trade_id": 1, "ts_exchange_ms": _START_MS + 60_000, "price": stop}]
    )

    report = replay_btc_absorption_signals(
        pd.DataFrame([_signal()]), books, trades, _zero_funding(), config
    )

    trade = report.trades.iloc[0]
    assert trade["exit_reason"] == "protective_stop_proxy"
    assert trade["exit_price"] == pytest.approx(target)
    assert bool(trade["same_timestamp_ambiguity"]) is True
    assert trade["exit_fee_rate"] == pytest.approx(0.00045)


def test_latency_stress_and_incomplete_capacity_are_explicit() -> None:
    """Stress latency must skip early books and reject insufficient asks."""
    config = BtcAbsorptionReplayConfig(
        entry_latency_ms=2_000,
        additional_entry_slippage_bps=3.0,
    )
    books = pd.DataFrame(
        [
            _book(500, bid=100.0, ask=100.1),
            _book(2_000, bid=100.9, ask=101.0, quantity=0.01),
        ]
    )

    report = replay_btc_absorption_signals(
        pd.DataFrame([_signal()]), books, _empty_trades(), _zero_funding(), config
    )

    assert report.trades.empty
    assert report.rejections == {"entry_visible_depth_incomplete": 1}


def test_maximum_hold_applies_long_funding_and_position_occupancy() -> None:
    """Funding must be side-correct and an open BTC position must block overlap."""
    config = BtcAbsorptionReplayConfig(maximum_hold_seconds=3_600)
    books = pd.DataFrame(
        [
            _book(500, bid=100.0, ask=100.1),
            _book(3_600_000, bid=100.0, ask=100.1),
            _book(3_600_500, bid=100.0, ask=100.1),
        ]
    )
    funding = pd.Series(
        [0.001],
        index=pd.DatetimeIndex([_START + pd.Timedelta(hours=1)]),
        name="funding_rate",
    )
    signals = pd.DataFrame(
        [_signal(event_id="first"), _signal(1_000, event_id="overlap")]
    )

    report = replay_btc_absorption_signals(
        signals, books, _empty_trades(), funding, config
    )

    assert len(report.trades) == 1
    trade = report.trades.iloc[0]
    assert trade["exit_reason"] == "maximum_hold"
    assert trade["funding_usd"] < 0.0
    assert report.rejections == {"symbol_position_open": 1}


def test_replay_rejects_duplicate_books_and_unsupported_stop_proxy() -> None:
    """Ambiguous market evidence and unregistered scenarios must fail closed."""
    duplicated = pd.DataFrame(
        [_book(500, bid=100.0, ask=100.1), _book(500, bid=100.0, ask=100.1)]
    )
    with pytest.raises(ValueError, match="unique"):
        replay_btc_absorption_signals(
            pd.DataFrame([_signal()]), duplicated, _empty_trades(), _zero_funding()
        )
    with pytest.raises(ValueError, match="stop trigger"):
        BtcAbsorptionReplayConfig(stop_trigger_proxy="mark")
