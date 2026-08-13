"""Sparse-window orchestration for continuous source-follow execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioEvent,
    SourcePortfolioReplayConfig,
    SourceSignal,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
)
from hypervector.research.source_follow_sparse_replay import (
    advance_sparse_source_portfolio,
    replay_sparse_source_portfolio,
)

_SIGNAL = datetime(2026, 7, 24, 13, 20, tzinfo=UTC)
_SIGNAL_MS = int(_SIGNAL.timestamp() * 1_000)


class _Archive:
    def __init__(self, events: tuple[SourcePortfolioEvent, ...]) -> None:
        self._events = events
        self.windows: list[tuple[datetime, datetime]] = []

    def events(
        self, start: datetime, end: datetime
    ) -> tuple[SourcePortfolioEvent, ...]:
        self.windows.append((start, end))
        lower = int(start.timestamp() * 1_000)
        upper = int(end.timestamp() * 1_000)
        return tuple(
            event for event in self._events if lower <= _event_ms(event) < upper
        )


def _event_ms(event: SourcePortfolioEvent) -> int:
    return event.exchange_ts_ms


def _book(offset: int) -> L2SnapshotEvent:
    timestamp = _SIGNAL_MS + offset
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=timestamp,
        received_ts_ns=timestamp * 1_000_000,
        bids=(BookLevel(100.0, 2.0, 1),),
        asks=(BookLevel(101.0, 2.0, 1),),
    )


def _trade(
    offset: int,
    trade_id: int,
    side: Literal["buy", "sell"],
    price: float,
    size: float,
) -> PublicTradeEvent:
    timestamp = _SIGNAL_MS + offset
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side=side,
        price=price,
        size=size,
        transaction_hash=f"0x{trade_id}",
        exchange_ts_ms=timestamp,
        received_ts_ns=timestamp * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )


def test_sparse_replay_skips_flat_hours_without_changing_execution() -> None:
    """Only idle gaps may be omitted from an otherwise continuous runtime."""
    archive = _Archive(
        (
            _book(0),
            _book(100),
            _trade(101, 1, "buy", 102.0, 3.0),
            _book(200),
            _trade(201, 2, "sell", 99.0, 3.0),
        )
    )
    config = SourcePortfolioReplayConfig(
        initial_equity=101.0,
        margin_fraction=1.0 / 30.0,
        leverage=30.0,
        target_price_fraction=1.0 / 101.0,
    )

    result = replay_sparse_source_portfolio(
        archive,
        _SIGNAL - timedelta(hours=1),
        _SIGNAL + timedelta(hours=1),
        (SourceSignal(_SIGNAL.isoformat()),),
        config,
    )

    assert result.report.completed_trades == 1
    assert result.report.final_equity > result.report.initial_equity
    assert result.queried_intervals == 1
    assert result.queried_seconds < result.window_seconds / 10.0


def test_sparse_segments_carry_one_portfolio_across_idle_data_gaps() -> None:
    """Segment boundaries may skip evidence only after the portfolio is flat."""
    second_signal = _SIGNAL + timedelta(hours=2)
    gap_ms = int(timedelta(hours=2).total_seconds() * 1_000)
    archive = _Archive(
        (
            _book(0),
            _book(100),
            _trade(101, 1, "buy", 102.0, 3.0),
            _book(200),
            _trade(201, 2, "sell", 99.0, 3.0),
            _book(gap_ms - 1_000),
            _book(gap_ms),
            _book(gap_ms + 100),
            _trade(gap_ms + 101, 3, "buy", 102.0, 3.0),
            _book(gap_ms + 200),
            _trade(gap_ms + 201, 4, "sell", 99.0, 3.0),
        )
    )
    config = SourcePortfolioReplayConfig(
        initial_equity=101.0,
        margin_fraction=1.0 / 30.0,
        leverage=30.0,
        target_price_fraction=1.0 / 101.0,
    )
    signals = (
        SourceSignal(_SIGNAL.isoformat()),
        SourceSignal(second_signal.isoformat()),
    )
    session = SourcePortfolioReplaySession(signals, config)

    first = advance_sparse_source_portfolio(
        session,
        archive,
        _SIGNAL - timedelta(minutes=1),
        _SIGNAL + timedelta(minutes=1),
        signals[:1],
    )
    first_equity = session.report().final_equity
    assert session.is_idle
    second = advance_sparse_source_portfolio(
        session,
        archive,
        second_signal - timedelta(minutes=1),
        second_signal + timedelta(minutes=1),
        signals[1:],
    )

    report = session.report()
    assert first.queried_intervals == 1
    assert second.queried_intervals == 1
    assert report.completed_trades == 2
    assert report.final_equity > first_equity > report.initial_equity
