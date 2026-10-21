"""Tests for the dedicated Hypervelocity Nautilus simulation configuration."""

from __future__ import annotations

from decimal import Decimal

import pytest
from nautilus_trader.backtest.models import (
    FillModel,
    LatencyModel,
    MakerTakerFeeModel,
    StandardMarginModel,
)
from nautilus_trader.model.enums import (
    AccountType,
    BookType,
    OmsType,
    OtoTriggerMode,
    OrderSide,
    OrderType,
)

from hypervector.nautilus.bars import synthetic_btc_perp_instrument
from hypervector.nautilus.hypervelocity_sim import (
    HypervelocitySimulationConfig,
    build_hypervelocity_venue,
    detect_nautilus_simulation_capabilities,
)
from nautilus_sim_support import (
    AggressiveLimitStrategy,
    CancelBeforeTradeStrategy,
    CrossingPostOnlyStrategy,
    PartialBracketStrategy,
    RecordingEngine,
    cancel_tape,
    market_data,
    new_engine,
    partial_fill_signature,
)


def test_hypervelocity_venue_enables_deterministic_event_friction() -> None:
    engine = RecordingEngine()
    config = HypervelocitySimulationConfig(
        submit_latency_ms=37,
        cancel_latency_ms=83,
        random_seed=19,
    )

    build_hypervelocity_venue(engine, init_cash=10_000.0, config=config)

    assert engine.arguments is not None
    args = engine.arguments
    assert args["account_type"] == AccountType.MARGIN
    assert args["oms_type"] == OmsType.NETTING
    assert args["default_leverage"] == Decimal("30")
    assert args["book_type"] == BookType.L2_MBP
    assert args["liquidity_consumption"] is True
    assert args["queue_position"] is True
    assert args["trade_execution"] is True
    assert args["bar_execution"] is False
    assert args["oto_trigger_mode"] == OtoTriggerMode.PARTIAL
    assert isinstance(args["fill_model"], FillModel)
    assert isinstance(args["fee_model"], MakerTakerFeeModel)
    assert isinstance(args["margin_model"], StandardMarginModel)

    latency = args["latency_model"]
    assert isinstance(latency, LatencyModel)
    assert latency.insert_latency_nanos == 37_000_000
    assert latency.cancel_latency_nanos == 83_000_000


def test_simulation_config_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="submit_latency_ms"):
        HypervelocitySimulationConfig(submit_latency_ms=-1)
    with pytest.raises(ValueError, match="default_leverage"):
        HypervelocitySimulationConfig(default_leverage=0)
    with pytest.raises(ValueError, match="maker_fill_probability"):
        HypervelocitySimulationConfig(maker_fill_probability=1.1)


def test_installed_nautilus_liquidation_gap_is_reported_not_hidden() -> None:
    capabilities = detect_nautilus_simulation_capabilities()

    assert capabilities.post_only_rejection
    assert capabilities.submit_cancel_latency
    assert capabilities.per_level_liquidity
    assert capabilities.queue_position
    assert capabilities.partial_oto_release
    assert not capabilities.proportional_target_resize
    assert "does not resize" in capabilities.proportional_target_detail
    assert not capabilities.native_liquidation
    assert "not forwarded" in capabilities.native_liquidation_detail


def test_same_configuration_produces_identical_models() -> None:
    config = HypervelocitySimulationConfig(
        submit_latency_ms=25,
        cancel_latency_ms=40,
        random_seed=7,
    )
    first = RecordingEngine()
    second = RecordingEngine()

    build_hypervelocity_venue(first, init_cash=120.0, config=config)
    build_hypervelocity_venue(second, init_cash=120.0, config=config)

    assert first.arguments is not None
    assert second.arguments is not None
    for key in (
        "account_type",
        "oms_type",
        "default_leverage",
        "book_type",
        "liquidity_consumption",
        "queue_position",
        "oto_trigger_mode",
    ):
        assert first.arguments[key] == second.arguments[key]
    first_latency = first.arguments["latency_model"]
    second_latency = second.arguments["latency_model"]
    assert isinstance(first_latency, LatencyModel)
    assert isinstance(second_latency, LatencyModel)
    assert first_latency.insert_latency_nanos == second_latency.insert_latency_nanos
    assert first_latency.cancel_latency_nanos == second_latency.cancel_latency_nanos


def test_nautilus_rejects_crossing_post_only_order() -> None:
    engine = new_engine()
    instrument = synthetic_btc_perp_instrument()
    strategy = CrossingPostOnlyStrategy(instrument.id)
    try:
        build_hypervelocity_venue(
            engine,
            init_cash=10_000.0,
            config=HypervelocitySimulationConfig(
                submit_latency_ms=0,
                cancel_latency_ms=0,
            ),
        )
        engine.add_instrument(instrument)
        engine.add_data(market_data(instrument.id))
        engine.add_strategy(strategy)

        engine.run()

        assert len(strategy.rejections) == 1
        assert strategy.rejections[0].due_post_only
        assert strategy.fills == []
    finally:
        engine.dispose()


def test_nautilus_consumes_l2_levels_and_assesses_partial_fill_fees() -> None:
    engine = new_engine()
    instrument = synthetic_btc_perp_instrument()
    strategy = AggressiveLimitStrategy(instrument.id)
    try:
        build_hypervelocity_venue(
            engine,
            init_cash=10_000.0,
            config=HypervelocitySimulationConfig(
                submit_latency_ms=0,
                cancel_latency_ms=0,
            ),
        )
        engine.add_instrument(instrument)
        engine.add_data(market_data(instrument.id, split_asks=True))
        engine.add_strategy(strategy)

        engine.run()

        assert len(strategy.acceptances) == 1
        assert [fill.last_px.as_double() for fill in strategy.fills] == [101.0, 102.0]
        assert [fill.last_qty.as_double() for fill in strategy.fills] == [2.0, 3.0]
        assert sum(
            fill.commission.as_double() for fill in strategy.fills
        ) == pytest.approx((2.0 * 101.0 + 3.0 * 102.0) * 0.00045)
        orders = engine.cache.orders()
        assert len(orders) == 1
        assert orders[0].filled_qty.as_double() == 5.0
        assert orders[0].leaves_qty.as_double() == 2.0
    finally:
        engine.dispose()


def test_cancel_latency_completes_before_later_trade_can_fill() -> None:
    engine = new_engine()
    instrument = synthetic_btc_perp_instrument()
    strategy = CancelBeforeTradeStrategy(instrument.id)
    try:
        build_hypervelocity_venue(
            engine,
            init_cash=10_000.0,
            config=HypervelocitySimulationConfig(
                submit_latency_ms=37,
                cancel_latency_ms=83,
            ),
        )
        engine.add_instrument(instrument)
        engine.add_data(cancel_tape(instrument.id))
        engine.add_strategy(strategy)

        engine.run()

        assert len(strategy.acceptances) == 1
        assert strategy.acceptances[0].ts_event - 1_000_000_000 >= 37_000_000
        assert len(strategy.cancellations) == 1
        assert strategy.cancel_requested_at is not None
        assert (
            strategy.cancellations[0].ts_event - strategy.cancel_requested_at
            >= 83_000_000
        )
        assert strategy.fills == []
    finally:
        engine.dispose()


def test_native_partial_oto_release_does_not_resize_target_quantity() -> None:
    engine = new_engine()
    instrument = synthetic_btc_perp_instrument()
    strategy = PartialBracketStrategy(instrument.id)
    try:
        build_hypervelocity_venue(
            engine,
            init_cash=10_000.0,
            config=HypervelocitySimulationConfig(
                submit_latency_ms=0,
                cancel_latency_ms=0,
            ),
        )
        engine.add_instrument(instrument)
        engine.add_data(market_data(instrument.id, split_asks=True))
        engine.add_strategy(strategy)

        engine.run()

        entry = next(
            order for order in engine.cache.orders() if order.side == OrderSide.BUY
        )
        target = next(
            order
            for order in engine.cache.orders()
            if order.side == OrderSide.SELL and order.order_type == OrderType.LIMIT
        )
        assert entry.filled_qty.as_double() == 5.0
        assert entry.leaves_qty.as_double() == 2.0
        assert target.quantity.as_double() == 7.0
        assert target.is_open
    finally:
        engine.dispose()


def test_event_tape_fill_and_fee_results_are_repeatable() -> None:
    first = partial_fill_signature()
    second = partial_fill_signature()

    assert first == second
    assert first == (
        (101.0, 2.0, 0.0909),
        (102.0, 3.0, 0.1377),
    )
