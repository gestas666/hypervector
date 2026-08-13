"""Hyperliquid isolated-margin and liquidation formula tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from nautilus_trader.backtest.models import (
    LeveragedMarginModel,
    StandardMarginModel,
)
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.objects import Price, Quantity

from hypervector.nautilus.bars import synthetic_btc_perp_instrument
from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPortfolio,
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.strategies.hypervelocity_contract import HypervelocityContract


def test_canary_allocation_and_btc_maintenance_requirement() -> None:
    allocation = HypervelocityContract().allocate(120.0)
    shadow = HypervelocityContract().allocate(10_000.0)
    rate = maintenance_rate_for_max_leverage(40.0)

    assert allocation.margin == pytest.approx(84.0)
    assert allocation.notional == pytest.approx(2_520.0)
    assert rate == pytest.approx(0.0125)
    assert allocation.notional * rate == pytest.approx(31.5)
    assert shadow.margin == pytest.approx(7_000.0)
    assert shadow.notional == pytest.approx(210_000.0)
    assert shadow.notional * rate == pytest.approx(2_625.0)


def test_liquidation_uses_mark_fees_and_signed_funding() -> None:
    entry_price = 64_500.0
    notional = 3_360.0
    position = IsolatedMarginPosition(
        symbol="BTC",
        side="long",
        quantity=notional / entry_price,
        entry_price=entry_price,
        isolated_margin=84.0,
        maintenance_rate=0.0125,
        fees_paid_usd=notional * 0.00015,
        funding_net_usd=-0.25,
    )

    liquidation_price = position.liquidation_price()
    at_boundary = position.state(liquidation_price)

    assert liquidation_price == pytest.approx(63_698.20, abs=0.02)
    assert at_boundary.equity_usd == pytest.approx(at_boundary.maintenance_margin_usd)
    assert at_boundary.liquidatable
    assert not position.state(liquidation_price + 0.1).liquidatable
    assert position.state(liquidation_price - 0.1).liquidatable


def test_short_liquidation_boundary_is_directionally_symmetric() -> None:
    position = IsolatedMarginPosition(
        symbol="BTC",
        side="short",
        quantity=3_360.0 / 64_500.0,
        entry_price=64_500.0,
        isolated_margin=84.0,
        maintenance_rate=0.0125,
    )

    liquidation_price = position.liquidation_price()

    assert liquidation_price == pytest.approx(65_296.30, abs=0.02)
    assert position.state(liquidation_price).liquidatable
    assert not position.state(liquidation_price - 0.1).liquidatable


def test_isolated_liquidation_does_not_consume_other_position_margin() -> None:
    btc = IsolatedMarginPosition(
        symbol="BTC",
        side="long",
        quantity=3_360.0 / 64_500.0,
        entry_price=64_500.0,
        isolated_margin=84.0,
        maintenance_rate=0.0125,
    )
    eth = IsolatedMarginPosition(
        symbol="ETH",
        side="long",
        quantity=1.0,
        entry_price=3_000.0,
        isolated_margin=120.0,
        maintenance_rate=0.02,
    )
    portfolio = IsolatedMarginPortfolio((btc, eth))

    evaluation = portfolio.evaluate(
        {"BTC": btc.liquidation_price() - 1.0, "ETH": 3_000.0}
    )

    assert evaluation.states["BTC"].liquidatable
    assert not evaluation.states["ETH"].liquidatable
    assert evaluation.states["ETH"].equity_usd == pytest.approx(120.0)
    assert evaluation.surviving_margin_usd == pytest.approx(120.0)


def test_nautilus_leveraged_default_mismatches_hyperliquid_margin() -> None:
    instrument = synthetic_btc_perp_instrument()
    quantity = Quantity.from_str("1.000")
    price = Price.from_str("3360.0")
    leverage = Decimal("40")
    leveraged = LeveragedMarginModel()
    standard = StandardMarginModel()

    default_initial = leveraged.calculate_margin_init(
        instrument, quantity, price, leverage
    )
    default_maintenance = leveraged.calculate_margin_maint(
        instrument, PositionSide.LONG, quantity, price, leverage
    )
    venue_initial = standard.calculate_margin_init(
        instrument, quantity, price, leverage
    )
    venue_maintenance = standard.calculate_margin_maint(
        instrument, PositionSide.LONG, quantity, price, leverage
    )

    assert default_initial.as_double() == pytest.approx(2.10)
    assert default_maintenance.as_double() == pytest.approx(1.05)
    assert venue_initial.as_double() == pytest.approx(84.0)
    assert venue_maintenance.as_double() == pytest.approx(42.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"quantity": 0.0},
        {"isolated_margin": 0.0},
        {"maintenance_rate": 0.0},
        {"maintenance_rate": 1.0},
        {"fees_paid_usd": -1.0},
    ],
)
def test_isolated_position_rejects_invalid_inputs(kwargs: dict[str, float]) -> None:
    values: dict[str, object] = {
        "symbol": "BTC",
        "side": "long",
        "quantity": 0.05,
        "entry_price": 64_500.0,
        "isolated_margin": 84.0,
        "maintenance_rate": 0.0125,
    }
    values.update(kwargs)

    with pytest.raises((TypeError, ValueError)):
        IsolatedMarginPosition(**values)
