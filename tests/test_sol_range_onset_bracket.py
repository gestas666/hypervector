"""Tests for exact owned stop/target bracket verification."""

from __future__ import annotations

from hypervector.live.hyperliquid_protocol import (
    SolAccountSnapshot,
    SolOpenOrder,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_range_onset_bracket import complete_bracket_visible


def test_bracket_accepts_officially_normalized_target_price() -> None:
    """A five-significant-figure venue price matches its raw target request."""
    venue = _venue(
        stop=_order(11, trigger=True, price=63_263.0),
        target=_order(22, trigger=False, price=63_770.0),
    )

    visible = complete_bracket_visible(
        venue,
        stop_oid=11,
        target_oid=22,
        position_size_signed=0.00039,
        target_price=63_770.340000000004,
    )

    assert visible is True


def _order(oid: int, *, trigger: bool, price: float) -> SolOpenOrder:
    return SolOpenOrder(
        oid=oid,
        size=0.00039,
        original_size=0.00039,
        side="A",
        reduce_only=True,
        is_trigger=trigger,
        trigger_price=price if trigger else 0.0,
        order_type="Stop Market" if trigger else "Limit",
        timestamp_ms=1,
        limit_price=price,
    )


def _venue(
    *,
    stop: SolOpenOrder,
    target: SolOpenOrder,
) -> SolReconciliationSnapshot:
    position = SolPositionSnapshot(
        size_signed=0.00039,
        entry_price=63_390.0,
        liquidation_price=51_381.0,
        margin_used_usd=4.9,
        position_value_usd=24.7,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated",
        leverage=5,
    )
    account = SolAccountSnapshot(
        account_value_usd=500.0,
        withdrawable_usd=495.0,
        total_margin_used_usd=4.9,
        total_notional_position_usd=24.7,
        position=position,
    )
    return SolReconciliationSnapshot(
        account=account,
        open_orders=(stop, target),
        fills=(),
    )
