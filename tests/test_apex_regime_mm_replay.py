"""Event-level execution contracts for the repaired Apex market maker."""

from __future__ import annotations

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent, PublicTradeEvent
from hypervector.research.apex_regime_mm_policy import ApexMMPolicyConfig
from hypervector.research.apex_regime_mm_replay import (
    ApexMMReplayConfig,
    FundingPoint,
    replay_apex_regime_mm_v2,
)


def _book(
    timestamp_ms: int,
    *,
    bid: float = 100.0,
    ask: float = 101.0,
    bid_size: float = 2.0,
    ask_size: float = 2.0,
) -> L2SnapshotEvent:
    event_timestamp_ms = timestamp_ms + 1
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=event_timestamp_ms,
        received_ts_ns=event_timestamp_ms * 1_000_000,
        bids=(BookLevel(bid, bid_size, 1),),
        asks=(BookLevel(ask, ask_size, 1),),
    )


def _trade(
    timestamp_ms: int,
    trade_id: int,
    *,
    side: str,
    price: float,
    size: float,
) -> PublicTradeEvent:
    event_timestamp_ms = timestamp_ms + 1
    return PublicTradeEvent(
        symbol="BTC",
        aggressor_side=side,
        price=price,
        size=size,
        transaction_hash=f"0x{trade_id}",
        exchange_ts_ms=event_timestamp_ms,
        received_ts_ns=event_timestamp_ms * 1_000_000,
        trade_id=trade_id,
        buyer="buyer",
        seller="seller",
    )


def _config(**overrides: object) -> ApexMMReplayConfig:
    values: dict[str, object] = {
        "policy": ApexMMPolicyConfig(
            tick_size=1.0,
            base_order_notional_usd=100.0,
            maximum_inventory_fraction=0.5,
        ),
        "initial_equity_usd": 15_000.0,
        "submit_latency_ms": 50,
        "cancel_latency_ms": 50,
        "quote_refresh_ms": 1_000,
        "markout_horizon_ms": 1_000,
        "leverage": 3.0,
    }
    values.update(overrides)
    return ApexMMReplayConfig(**values)


def test_trade_through_consumes_displayed_queue_before_partial_maker_fills() -> None:
    events = (
        _book(0),
        _trade(10, 1, side="sell", price=100.0, size=10.0),
        _trade(60, 2, side="sell", price=100.0, size=2.5),
        _trade(70, 3, side="sell", price=100.0, size=1.0),
        _book(2_000),
    )

    result = replay_apex_regime_mm_v2(events, (), _config())

    maker_buys = [
        fill
        for fill in result.fills
        if fill.liquidity_side == "maker" and fill.side == "buy"
    ]
    assert [fill.timestamp_ms for fill in maker_buys] == [61, 71]
    assert maker_buys[0].quantity == 0.5
    assert sum(fill.quantity for fill in maker_buys) > 0.99
    assert result.queue_depleted_quantity >= 2.0
    assert result.final_inventory_qty == 0.0
    assert result.taker_fill_count == 1


def test_aggressor_buy_only_depletes_the_resting_ask() -> None:
    events = (
        _book(0, bid_size=1.0, ask_size=1.0),
        _trade(60, 1, side="buy", price=101.0, size=2.0),
        _book(2_000),
    )

    result = replay_apex_regime_mm_v2(events, (), _config())

    maker = [fill for fill in result.fills if fill.liquidity_side == "maker"]
    assert len(maker) == 1
    assert maker[0].side == "sell"


def test_order_remains_fillable_until_cancel_latency_elapses() -> None:
    events = (
        _book(0, bid_size=1.0, ask_size=1.0),
        _book(1_000, bid=101.0, ask=102.0, bid_size=1.0, ask_size=1.0),
        _trade(1_025, 1, side="sell", price=100.0, size=2.0),
        _book(2_100, bid=101.0, ask=102.0),
    )

    result = replay_apex_regime_mm_v2(events, (), _config())

    maker_buys = [
        fill
        for fill in result.fills
        if fill.liquidity_side == "maker" and fill.side == "buy"
    ]
    assert len(maker_buys) == 1
    assert maker_buys[0].timestamp_ms == 1_026


def test_replay_accounts_for_maker_taker_fees_and_hourly_funding() -> None:
    events = (
        _book(0, bid_size=1.0, ask_size=1.0),
        _trade(60, 1, side="sell", price=100.0, size=2.0),
        _book(1_000),
        _book(2_000),
    )
    funding = (FundingPoint(timestamp_ms=500, hourly_rate=0.001),)

    result = replay_apex_regime_mm_v2(events, funding, _config())

    assert result.maker_fees_usd > 0.0
    assert result.taker_fees_usd > 0.0
    assert result.funding_cashflow_usd < 0.0
    assert result.net_pnl_usd < 0.0
    assert result.execution_authority == "none"
    assert not result.place_attempted
    assert {fill.strategy_id for fill in result.fills} == {"apex_regime_mm_v2"}


def test_replay_records_adverse_markout_and_liquidation_distance() -> None:
    events = (
        _book(0, bid_size=1.0, ask_size=1.0),
        _trade(60, 1, side="sell", price=100.0, size=2.0),
        _book(1_100, bid=98.0, ask=99.0),
        _book(2_000, bid=98.0, ask=99.0),
    )

    result = replay_apex_regime_mm_v2(events, (), _config())

    maker_buy = next(
        fill
        for fill in result.fills
        if fill.liquidity_side == "maker" and fill.side == "buy"
    )
    assert maker_buy.markout_bps is not None
    assert maker_buy.markout_bps < 0.0
    assert result.minimum_liquidation_distance_pct is not None
    assert result.minimum_liquidation_distance_pct > 0.0
    assert result.liquidations == 0


def test_replay_rejects_unordered_events() -> None:
    events = (_book(100), _book(0))

    try:
        replay_apex_regime_mm_v2(events, (), _config())
    except ValueError as error:
        assert "chronological" in str(error)
    else:
        raise AssertionError("unordered evidence was accepted")
