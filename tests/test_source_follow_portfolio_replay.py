"""Continuous production-matcher replay for source-follow portfolios."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
    SourcePortfolioReplayConfig,
    SourceReplayFunding,
    SourceReplayMark,
    SourceSignal,
    replay_source_portfolio,
)

_START = datetime(2026, 7, 24, 13, 20, tzinfo=UTC)
_START_MS = int(_START.timestamp() * 1_000)


def _book(
    offset_ms: int,
    *,
    bid: float = 100.0,
    ask: float = 101.0,
    bid_size: float = 2.0,
    ask_size: float = 2.0,
) -> L2SnapshotEvent:
    timestamp = _START_MS + offset_ms
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=timestamp,
        received_ts_ns=timestamp * 1_000_000,
        bids=(BookLevel(bid, bid_size, 1),),
        asks=(BookLevel(ask, ask_size, 1),),
    )


def _trade(
    offset_ms: int,
    trade_id: int,
    *,
    side: Literal["buy", "sell"],
    price: float,
    size: float,
) -> PublicTradeEvent:
    timestamp = _START_MS + offset_ms
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


def _config(*, initial_equity: float = 101.0) -> SourcePortfolioReplayConfig:
    return SourcePortfolioReplayConfig(
        initial_equity=initial_equity,
        margin_fraction=1.0 / 30.0,
        leverage=30.0,
        target_price_fraction=1.0 / 101.0,
    )


def test_continuous_replay_consumes_entry_and_target_queue() -> None:
    """Portfolio replay must use the production queue and fee implementation."""
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="buy", price=102.0, size=2.0),
        _trade(102, 2, side="buy", price=102.0, size=1.0),
        _book(200),
        _trade(201, 3, side="sell", price=99.0, size=2.0),
        _trade(202, 4, side="sell", price=99.0, size=1.0),
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat()),),
        _config(),
    )

    assert report.submitted_entries == 1
    assert report.entry_filled_quantity == pytest.approx(1.0)
    assert report.completed_trades == 1
    assert report.target_completions == 1
    assert report.liquidations == 0
    assert report.final_equity == pytest.approx(101.96985)
    assert report.trades[0].status == "target_completed"
    assert report.trades[0].net_pnl == pytest.approx(0.96985)
    assert report.trades[0].signal_time_utc == _START.isoformat()
    assert report.trades[0].entry_price == pytest.approx(101.0)
    assert report.trades[0].entry_quantity == pytest.approx(1.0)
    expected_liquidation = IsolatedMarginPosition(
        symbol="BTC",
        side="short",
        quantity=1.0,
        entry_price=101.0,
        isolated_margin=101.0 / 30.0,
        maintenance_rate=maintenance_rate_for_max_leverage(30.0),
        fees_paid_usd=101.0 * 0.00015,
    ).liquidation_price()
    assert report.trades[0].liquidation_price == pytest.approx(expected_liquidation)


def test_signal_allocation_multiplier_scales_entry_quantity() -> None:
    """A causal signal risk annotation may reduce size without suppressing entry."""
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="buy", price=102.0, size=2.0),
        _trade(102, 2, side="buy", price=102.0, size=1.0),
        _book(200),
        _trade(201, 3, side="sell", price=99.0, size=2.0),
        _trade(202, 4, side="sell", price=99.0, size=1.0),
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat(), allocation_multiplier=0.5),),
        _config(),
    )

    assert report.submitted_entries == 1
    assert report.entry_filled_quantity == pytest.approx(0.5)
    assert report.target_completions == 1
    assert report.final_equity == pytest.approx(101.484925)


def test_recorded_receive_timestamp_evidence_is_reported_truthfully() -> None:
    """Live reports must not claim their receipt timestamps are synthetic."""
    default = SourcePortfolioReplayConfig()
    assert hasattr(default, "receipt_timestamp_source")
    config = SourcePortfolioReplayConfig(receipt_timestamp_source="recorded")

    report = replay_source_portfolio((), (), config)

    assert "Recorder receive timestamps are preserved." in report.limitations
    assert all(
        "receipt timestamps equal exchange timestamps" not in text
        for text in report.limitations
    )


def test_continuous_replay_consumes_long_entry_and_target_queue() -> None:
    """A long challenger must use the same production queue and fee path."""
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="sell", price=99.0, size=2.0),
        _trade(102, 2, side="sell", price=99.0, size=1.0),
        _book(200),
        _trade(201, 3, side="buy", price=102.0, size=2.0),
        _trade(202, 4, side="buy", price=102.0, size=1.0),
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat(), direction="long"),),
        _config(),
    )

    assert report.submitted_entries == 1
    assert report.entry_filled_quantity == pytest.approx(1.0)
    assert report.completed_trades == 1
    assert report.target_completions == 1
    assert report.final_equity == pytest.approx(101.96985)
    assert report.trades[0].direction == "long"
    expected_liquidation = IsolatedMarginPosition(
        symbol="BTC",
        side="long",
        quantity=1.0,
        entry_price=100.0,
        isolated_margin=100.0 / 30.0,
        maintenance_rate=maintenance_rate_for_max_leverage(30.0),
        fees_paid_usd=100.0 * 0.00015,
    ).liquidation_price()
    assert report.trades[0].liquidation_price == pytest.approx(expected_liquidation)


def test_continuous_replay_reports_final_partial_entry_economics() -> None:
    """Lifecycle telemetry must use the completed entry, not its first fragment."""
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="buy", price=102.0, size=2.5),
        _trade(102, 2, side="buy", price=102.0, size=0.5),
        _book(200),
        _trade(201, 3, side="sell", price=99.0, size=10.0),
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat()),),
        _config(),
    )

    trade = report.trades[0]
    assert trade.entry_price == pytest.approx(101.0)
    assert trade.entry_quantity == pytest.approx(1.0)
    assert trade.signal_time_utc == _START.isoformat()


def test_continuous_replay_applies_mark_liquidation() -> None:
    """A fresh adverse mark must close a small isolated position."""
    events = (
        _book(0, ask_size=0.1),
        _book(100, ask_size=0.1),
        _trade(101, 1, side="buy", price=102.0, size=10.1),
        _book(200, bid=104.0, ask=104.1, bid_size=20.0, ask_size=20.0),
        SourceReplayMark(_START_MS + 201, 104.0, 104.0),
    )
    config = SourcePortfolioReplayConfig(
        initial_equity=1_000.0,
        margin_fraction=1.0 / 30.0,
        leverage=30.0,
        target_price_fraction=1.0 / 101.0,
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat()),),
        config,
    )

    assert report.completed_trades == 1
    assert report.liquidations == 1
    assert report.open_positions == 0
    assert report.trades[0].status == "liquidated"
    assert report.final_equity < report.initial_equity


def test_continuous_replay_books_short_funding_before_target() -> None:
    """Positive funding must increase a short portfolio before its close."""
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="buy", price=102.0, size=3.0),
        _book(200),
        SourceReplayMark(_START_MS + 201, 100.0, 100.0),
        SourceReplayFunding(_START_MS + 202, 0.001),
        _book(300),
        _trade(301, 2, side="sell", price=99.0, size=3.0),
    )

    report = replay_source_portfolio(
        events,
        (SourceSignal(_START.isoformat()),),
        _config(),
    )

    assert report.funding_cashflow == pytest.approx(0.1)
    assert report.final_equity == pytest.approx(102.06985)
    assert report.trades[0].funding_cashflow == pytest.approx(0.1)


def test_replay_session_exposes_idle_boundary_for_sparse_archive_windows() -> None:
    """Sparse archive orchestration may skip data only while execution is idle."""
    session = SourcePortfolioReplaySession(
        (SourceSignal(_START.isoformat()),),
        _config(),
    )
    assert session.is_idle

    for event in (_book(0), _book(100)):
        session.apply(event)
    assert not session.is_idle

    for event in (
        _trade(101, 1, side="buy", price=102.0, size=3.0),
        _book(200),
        _trade(201, 2, side="sell", price=99.0, size=3.0),
    ):
        session.apply(event)

    assert session.is_idle
    assert session.report().completed_trades == 1
