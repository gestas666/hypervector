"""Paper CostProvider: HL fee tiers + signed funding math (SRS_HV3P_*)."""

from __future__ import annotations

import pytest

from hypervector.paper.costs import (
    HL_PERP_FEE_TIERS,
    CostProvider,
    fees_for_tier,
    funding_payment,
)


def test_tier0_matches_official_base():
    taker, maker = fees_for_tier(0)
    assert taker == 0.00045
    assert maker == 0.00015
    assert HL_PERP_FEE_TIERS[0] == (0.00045, 0.00015)


def test_funding_payment_long_pays_when_rate_positive():
    # qty > 0 long, rate > 0 → positive payment means paid by long (cash drag)
    pay = funding_payment(
        position_qty=1.0, oracle_px=100_000.0, funding_rate_hourly=0.0001, hours=1.0
    )
    assert pay == 10.0  # 1 * 100000 * 0.0001


def test_funding_payment_short_receives_when_rate_positive():
    pay = funding_payment(
        position_qty=-1.0, oracle_px=100_000.0, funding_rate_hourly=0.0001, hours=1.0
    )
    assert pay == -10.0  # short receives


def test_cost_provider_snapshot_fields():
    cp = CostProvider(fee_tier=0, slippage_bps=2.0)
    snap = cp.snapshot()
    assert snap.taker_fee == 0.00045
    assert snap.maker_fee == 0.00015
    assert snap.slippage_bps == 2.0
    assert snap.fill_model_id == "bar_close_slippage_v1"
    assert isinstance(snap.sources, dict)


def test_fees_for_tier_unknown_raises():
    with pytest.raises(ValueError, match="unknown fee_tier"):
        fees_for_tier(99)


def test_cost_provider_trade_fee_rate_respects_assume_taker():
    taker_cp = CostProvider(fee_tier=0, assume_taker=True)
    maker_cp = CostProvider(fee_tier=0, assume_taker=False)
    assert taker_cp.trade_fee_rate() == 0.00045
    assert maker_cp.trade_fee_rate() == 0.00015
