"""Causal maker-entry reconstruction for the 15-minute Hulk challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.market_cipher_maker_entry import (
    MakerEntryConfig,
    MakerEntryRequest,
    build_maker_replay_signal,
    reconstruct_maker_entry,
)


def _books() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_exchange_ms": 60_100,
                "best_bid": 100.0,
                "best_ask": 101.0,
                "bids": [{"px": 100.0, "sz": 2.0}],
                "asks": [{"px": 101.0, "sz": 3.0}],
            }
        ]
    )


def _request(direction: str = "long") -> MakerEntryRequest:
    return MakerEntryRequest(
        decision_time_ms=60_000,
        direction=direction,
        quantity=0.5,
        original_entry_price=101.0 if direction == "long" else 100.0,
        stop_anchor=99.0 if direction == "long" else 102.0,
        signal_score=8.0,
    )


def test_long_fill_requires_displayed_queue_and_order_quantity() -> None:
    """Opposite-aggressor volume at the bid must clear queue plus our order."""
    trades = pd.DataFrame(
        [
            {
                "ts_exchange_ms": 61_000,
                "aggressor_side": "sell",
                "price": 100.0,
                "size": 1.0,
            },
            {
                "ts_exchange_ms": 62_000,
                "aggressor_side": "sell",
                "price": 100.0,
                "size": 1.6,
            },
        ]
    )

    outcome = reconstruct_maker_entry(_request(), _books(), trades)

    assert outcome.status == "filled"
    assert outcome.limit_price == 100.0
    assert outcome.fill_time_ms == 62_000
    assert outcome.entry_improvement_bps == pytest.approx(99.00990099)


def test_wrong_aggressor_or_insufficient_volume_does_not_fill() -> None:
    """A crossed-looking print cannot fill the wrong resting side."""
    trades = pd.DataFrame(
        [
            {
                "ts_exchange_ms": 61_000,
                "aggressor_side": "buy",
                "price": 99.0,
                "size": 10.0,
            },
            {
                "ts_exchange_ms": 62_000,
                "aggressor_side": "sell",
                "price": 100.0,
                "size": 2.4,
            },
        ]
    )

    outcome = reconstruct_maker_entry(_request(), _books(), trades)

    assert outcome.status == "unfilled"
    assert outcome.observed_trade_volume == pytest.approx(2.4)


def test_stale_first_book_is_reported_instead_of_used() -> None:
    """A future snapshot outside the configured delay is missing evidence."""
    delayed = _books().copy()
    delayed["ts_exchange_ms"] = 61_001

    outcome = reconstruct_maker_entry(
        _request(),
        delayed,
        pd.DataFrame(),
        MakerEntryConfig(maximum_book_delay_ms=1_000),
    )

    assert outcome.status == "missing_book"


def test_replay_signal_starts_after_the_fill_minute_and_keeps_exact_price() -> None:
    """Lifecycle bars cannot include price action that occurred before the fill."""
    trades = pd.DataFrame(
        [
            {
                "ts_exchange_ms": 62_000,
                "aggressor_side": "sell",
                "price": 99.0,
                "size": 3.0,
            }
        ]
    )
    outcome = reconstruct_maker_entry(_request(), _books(), trades)

    signal = build_maker_replay_signal(_request(), outcome, candidate="maker_probe")

    assert signal["signal_time_utc"] == pd.Timestamp(60_000, unit="ms", tz="UTC")
    assert signal["entry_price_override"] == 100.0
    assert signal["side"] == "long"


def test_unfilled_outcome_cannot_become_a_replay_signal() -> None:
    """An expired maker order may not silently fall back to a market entry."""
    outcome = reconstruct_maker_entry(_request(), _books(), pd.DataFrame())

    with pytest.raises(ValueError, match="filled maker outcome"):
        build_maker_replay_signal(_request(), outcome, candidate="maker_probe")
