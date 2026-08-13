"""Prospective HIP-3 candle-source signal parity tests."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
from pytest import raises

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_prospective_signal_parity import (
    Hip3ProspectiveSignalParityConfig,
    build_hip3_prospective_signal_parity,
)

_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_SYMBOL = "xyz:MU"


def test_exact_candle_sources_produce_equivalent_strategy_decisions() -> None:
    bars = _bars()

    report = build_hip3_prospective_signal_parity(
        trade_bars=bars,
        venue_bars=bars.copy(),
        l2_snapshots=_books(),
        observed_at_ms=_end_ms(),
        config=_config(),
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["source"]["pressure_source"] == "hyperliquid_ws_l2Book"
    assert report["coverage"]["warmup_complete"] is True
    assert report["coverage"]["fresh_pressure_decision_bars"] == 3
    assert report["coverage"]["decision_start_ms"] == _START_MS + 3 * _BAR_MS
    assert report["coverage"]["decision_end_ms"] == _START_MS + 5 * _BAR_MS
    assert report["coverage"]["eventful_decision_bars"] == 3
    assert report["coverage"]["trade_entry_events"] == 1
    assert report["coverage"]["venue_entry_events"] == 1
    expected_entry = {
        "bar_open_ms": _START_MS + 3 * _BAR_MS,
        "decision_time_ms": _START_MS + 4 * _BAR_MS,
        "side": "long",
    }
    assert report["reconstructed_entry_events"] == {
        "trade": [expected_entry],
        "venue": [expected_entry],
    }
    assert report["reconstructed_pressure_decisions"][-1] == {
        "bar_open_ms": _START_MS + 4 * _BAR_MS,
        "decision_time_ms": _START_MS + 5 * _BAR_MS,
        "end_boundary_age_ms": 1_000,
        "fresh": True,
        "imbalance_10": 0.8,
        "last_exchange_ts_ms": _START_MS + 5 * _BAR_MS - 1_000,
        "snapshot_count": 2,
    }
    assert report["signal_diagnostics"] == []
    assert report["technical_assessment"] == {
        "prospective_signal_source_parity_resolved": True,
        "prospective_entry_signal_parity_non_vacuous": True,
        "unresolved_pressure_bars": 0,
        "signal_disagreement_bars": 0,
    }


def test_close_difference_that_changes_entry_is_not_success_shaped() -> None:
    trade_bars = _bars()
    venue_bars = trade_bars.copy()
    venue_bars.loc[venue_bars.index[3], "close"] = 102.0

    report = build_hip3_prospective_signal_parity(
        trade_bars=trade_bars,
        venue_bars=venue_bars,
        l2_snapshots=_books(),
        observed_at_ms=_end_ms(),
        config=_config(),
    )

    assert report["coverage"]["entry_disagreement_bars"] == 1
    assert (
        report["technical_assessment"]["prospective_signal_source_parity_resolved"]
        is False
    )
    assert report["signal_diagnostics"][0]["mismatched_fields"] == ["long_entry"]


def test_insufficient_slow_ema_history_cannot_establish_signal_parity() -> None:
    bars = _bars().iloc[:2]

    report = build_hip3_prospective_signal_parity(
        trade_bars=bars,
        venue_bars=bars.copy(),
        l2_snapshots=_books()[:4],
        observed_at_ms=_START_MS + 2 * _BAR_MS,
        config=_config(),
    )

    assert report["coverage"]["warmup_complete"] is False
    assert report["coverage"]["decision_start_ms"] is None
    assert report["coverage"]["decision_end_ms"] is None
    assert (
        report["technical_assessment"]["prospective_signal_source_parity_resolved"]
        is False
    )


def test_matching_no_action_rows_are_explicitly_vacuous() -> None:
    bars = _bars()
    flat_books = tuple(
        replace(book, bids=_flat_bids(), asks=_flat_asks()) for book in _books()
    )

    report = build_hip3_prospective_signal_parity(
        trade_bars=bars,
        venue_bars=bars.copy(),
        l2_snapshots=flat_books,
        observed_at_ms=_end_ms(),
        config=_config(),
    )

    assert report["coverage"]["trade_entry_events"] == 0
    assert report["coverage"]["venue_entry_events"] == 0
    assert (
        report["technical_assessment"]["prospective_entry_signal_parity_non_vacuous"]
        is False
    )


def test_stale_ready_bar_pressure_keeps_signal_parity_unresolved() -> None:
    books = list(_books())
    ready_open = _START_MS + 4 * _BAR_MS
    books[-2] = replace(books[-2], exchange_ts_ms=ready_open + 100_000)
    books[-1] = replace(books[-1], exchange_ts_ms=ready_open + 200_000)

    report = build_hip3_prospective_signal_parity(
        trade_bars=_bars(),
        venue_bars=_bars(),
        l2_snapshots=tuple(books),
        observed_at_ms=_end_ms(),
        config=_config(),
    )

    assert report["technical_assessment"]["unresolved_pressure_bars"] == 1
    assert (
        report["technical_assessment"]["prospective_signal_source_parity_resolved"]
        is False
    )


def test_conflicting_same_timestamp_books_are_rejected() -> None:
    books = _books()
    conflict = replace(books[-1], bids=(_level(99.0, 20.0),) + books[-1].bids[1:])

    with raises(ValueError, match="conflicting L2 exchange timestamp"):
        build_hip3_prospective_signal_parity(
            trade_bars=_bars(),
            venue_bars=_bars(),
            l2_snapshots=books + (conflict,),
            observed_at_ms=_end_ms(),
            config=_config(),
        )


def _config() -> Hip3ProspectiveSignalParityConfig:
    return Hip3ProspectiveSignalParityConfig(
        symbol=_SYMBOL,
        provider_id="hip3_mu_signal_parity_test_v1",
        profile_id="mu_signal_parity_test_v1",
        breakout=Hip3BreakoutPressureConfig(2, 2, 3, 0.1, 80.0),
    )


def _bars() -> pd.DataFrame:
    index = pd.to_datetime(
        [_START_MS + offset * _BAR_MS for offset in range(5)], unit="ms", utc=True
    )
    close = [100.0, 101.0, 102.0, 104.0, 103.0]
    return pd.DataFrame(
        {
            "open": close,
            "high": [100.5, 101.5, 102.5, 104.5, 103.5],
            "low": [99.5, 100.5, 101.5, 101.5, 102.5],
            "close": close,
        },
        index=index,
    )


def _books() -> tuple[L2SnapshotEvent, ...]:
    rows: list[L2SnapshotEvent] = []
    for offset in range(5):
        bar_open = _START_MS + offset * _BAR_MS
        for intra_bar in (bar_open + 100_000, bar_open + _BAR_MS - 1_000):
            rows.append(_book(intra_bar, positive=offset >= 3))
    return tuple(rows)


def _book(timestamp_ms: int, *, positive: bool) -> L2SnapshotEvent:
    bid_size, ask_size = (9.0, 1.0) if positive else (5.0, 5.0)
    return L2SnapshotEvent(
        _SYMBOL,
        timestamp_ms,
        timestamp_ms * 1_000_000 + 1_000,
        tuple(_level(99.0 - offset, bid_size) for offset in range(10)),
        tuple(_level(101.0 + offset, ask_size) for offset in range(10)),
    )


def _level(price: float, size: float) -> BookLevel:
    return BookLevel(price, size, 1)


def _flat_bids() -> tuple[BookLevel, ...]:
    return tuple(_level(99.0 - offset, 5.0) for offset in range(10))


def _flat_asks() -> tuple[BookLevel, ...]:
    return tuple(_level(101.0 + offset, 5.0) for offset in range(10))


def _end_ms() -> int:
    return _START_MS + 5 * _BAR_MS
