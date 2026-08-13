"""Quote-policy contracts for the repaired Apex regime market maker."""

from __future__ import annotations

import pytest

from hypervector.research.apex_regime_mm_policy import (
    ApexMMMarketState,
    ApexMMPolicyConfig,
    quote_apex_regime_mm_v2,
)


def _state(**overrides: object) -> ApexMMMarketState:
    values: dict[str, object] = {
        "best_bid": 100.0,
        "best_ask": 101.0,
        "best_bid_size": 9.0,
        "best_ask_size": 1.0,
        "volatility_bps": 2.0,
        "inventory_qty": 0.0,
        "equity_usd": 15_000.0,
        "book_age_ms": 10,
        "cascade_side": "none",
    }
    values.update(overrides)
    return ApexMMMarketState(**values)


def test_policy_uses_l2_microprice_and_covers_round_trip_maker_fees() -> None:
    config = ApexMMPolicyConfig(tick_size=0.1, minimum_edge_bps=1.0)

    quote = quote_apex_regime_mm_v2(_state(), config)

    assert quote.active
    assert quote.fair_value == pytest.approx(100.9)
    assert quote.full_spread_bps >= 2.0 * config.maker_fee_rate * 10_000 + 1.0
    assert quote.bid_price is not None and quote.bid_price <= 100.0
    assert quote.ask_price is not None and quote.ask_price >= 101.0
    assert quote.bid_price < quote.ask_price


def test_policy_widens_quotes_as_observed_volatility_increases() -> None:
    config = ApexMMPolicyConfig(tick_size=0.1)

    calm = quote_apex_regime_mm_v2(_state(volatility_bps=1.0), config)
    volatile = quote_apex_regime_mm_v2(_state(volatility_bps=20.0), config)

    assert volatile.full_spread_bps > calm.full_spread_bps


def test_long_inventory_skews_prices_and_sizes_toward_flat() -> None:
    config = ApexMMPolicyConfig(
        tick_size=0.1,
        maximum_inventory_fraction=0.5,
        base_order_notional_usd=1_000.0,
    )
    flat = quote_apex_regime_mm_v2(_state(), config)
    long = quote_apex_regime_mm_v2(_state(inventory_qty=50.0), config)

    assert long.fair_value < flat.fair_value
    assert long.bid_size < flat.bid_size
    assert long.ask_size > flat.ask_size


def test_hard_inventory_cap_disables_exposure_increasing_quote() -> None:
    config = ApexMMPolicyConfig(
        tick_size=0.1,
        maximum_inventory_fraction=0.5,
        base_order_notional_usd=1_000.0,
    )

    long = quote_apex_regime_mm_v2(_state(inventory_qty=75.0), config)
    short = quote_apex_regime_mm_v2(_state(inventory_qty=-75.0), config)

    assert long.bid_size == 0.0
    assert long.ask_size > 0.0
    assert short.ask_size == 0.0
    assert short.bid_size > 0.0


def test_stale_book_refuses_to_quote() -> None:
    config = ApexMMPolicyConfig(maximum_book_age_ms=1_000)

    quote = quote_apex_regime_mm_v2(_state(book_age_ms=1_001), config)

    assert not quote.active
    assert quote.reason == "stale_book"
    assert quote.bid_price is None
    assert quote.ask_price is None
    assert quote.bid_size == 0.0
    assert quote.ask_size == 0.0


def test_cascade_reduces_the_toxic_side_and_widens_quotes() -> None:
    config = ApexMMPolicyConfig(tick_size=0.1, cascade_size_multiplier=0.2)
    normal = quote_apex_regime_mm_v2(_state(), config)

    down = quote_apex_regime_mm_v2(_state(cascade_side="down"), config)
    up = quote_apex_regime_mm_v2(_state(cascade_side="up"), config)

    assert down.bid_size == pytest.approx(normal.bid_size * 0.2)
    assert down.ask_size == pytest.approx(normal.ask_size)
    assert up.ask_size == pytest.approx(normal.ask_size * 0.2)
    assert up.bid_size == pytest.approx(normal.bid_size)
    assert down.full_spread_bps > normal.full_spread_bps


def test_quote_suppresses_a_leg_below_the_venue_minimum_notional() -> None:
    config = ApexMMPolicyConfig(
        tick_size=0.1,
        base_order_notional_usd=12.5,
        minimum_order_notional_usd=10.0,
        cascade_size_multiplier=0.25,
    )

    down = quote_apex_regime_mm_v2(_state(cascade_side="down"), config)

    assert down.bid_size == 0.0
    assert down.ask_size * 100.5 >= 10.0


def test_policy_rejects_crossed_or_invalid_market_state() -> None:
    with pytest.raises(ValueError, match="best bid"):
        quote_apex_regime_mm_v2(_state(best_bid=101.0, best_ask=101.0))
    with pytest.raises(ValueError, match="equity"):
        quote_apex_regime_mm_v2(_state(equity_usd=0.0))
