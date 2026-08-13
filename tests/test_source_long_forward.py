"""Forward-only source-long outcome evaluation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import pytest

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioReplayConfig,
)
from hypervector.research.source_long_forward import (
    SourceLongForwardSpec,
    evaluate_source_long_forward,
)

_START = datetime(2026, 7, 31, 13, 20, tzinfo=UTC)
_START_MS = int(_START.timestamp() * 1_000)


def _book(
    offset_ms: int,
    *,
    bid: float = 100.0,
    ask: float = 101.0,
    size: float = 2.0,
) -> L2SnapshotEvent:
    timestamp = _START_MS + offset_ms
    level_bid = BookLevel(bid, size, 1)
    level_ask = BookLevel(ask, size, 1)
    return L2SnapshotEvent(
        "BTC",
        timestamp,
        timestamp * 1_000_000,
        (level_bid,),
        (level_ask,),
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
        "BTC",
        side,
        price,
        size,
        f"0x{trade_id}",
        timestamp,
        timestamp * 1_000_000,
        trade_id,
        "buyer",
        "seller",
    )


def _context(offset_ms: int, *, funding: float = 0.001) -> AssetContextEvent:
    timestamp = _START_MS + offset_ms
    return AssetContextEvent(
        "BTC",
        timestamp,
        timestamp * 1_000_000,
        100.0,
        100.0,
        funding,
        10_000.0,
        100.5,
    )


def _config() -> SourcePortfolioReplayConfig:
    return SourcePortfolioReplayConfig(
        initial_equity=101.0,
        margin_fraction=1.0 / 30.0,
        leverage=30.0,
        target_price_fraction=1.0 / 101.0,
        receipt_timestamp_source="recorded",
    )


def _spec() -> SourceLongForwardSpec:
    return SourceLongForwardSpec(
        recipe_id="fade_td_eu",
        signal_time_utc=_START.isoformat(),
        maximum_hold_seconds=86_400.0,
    )


def test_forward_long_uses_maker_trade_through_and_hourly_funding() -> None:
    events = (
        _book(0),
        _book(100),
        _trade(101, 1, side="sell", price=99.0, size=2.0),
        _trade(102, 2, side="sell", price=99.0, size=1.0),
        _context(40 * 60 * 1_000),
        _book(40 * 60 * 1_000 + 100),
        _trade(
            40 * 60 * 1_000 + 101,
            3,
            side="buy",
            price=102.0,
            size=2.0,
        ),
        _trade(
            40 * 60 * 1_000 + 102,
            4,
            side="buy",
            price=102.0,
            size=1.0,
        ),
    )

    result = evaluate_source_long_forward(events, _spec(), _config())

    assert result.status == "target_completed"
    assert result.evidence_complete is True
    assert result.report.target_completions == 1
    assert result.report.funding_cashflow == pytest.approx(-0.1)
    assert result.report.final_equity == pytest.approx(101.86985)
    assert result.report.trades[0].direction == "long"


def test_forward_long_reports_no_fill_only_after_maker_ttl_resolves() -> None:
    events = (_book(0), _book(100), _book(61_000), _book(62_000))

    result = evaluate_source_long_forward(events, _spec(), _config())

    assert result.status == "no_fill"
    assert result.report.submitted_entries == 1
    assert result.report.entry_filled_quantity == 0.0
    assert result.report.completed_trades == 0


def test_active_stream_gap_marks_outcome_unfit_for_promotion() -> None:
    gap = StreamGap(
        "BTC",
        "l2Book,trades,activeAssetCtx",
        (_START_MS + 50) * 1_000_000,
        "websocket_reconnect",
        _START_MS,
        _START_MS + 100,
    )
    events = (_book(0), gap, _book(100), _book(62_000))

    result = evaluate_source_long_forward(events, _spec(), _config())

    assert result.active_stream_gaps == 1
    assert result.evidence_complete is False
