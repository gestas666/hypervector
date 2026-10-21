"""Reusable deterministic execution fixtures for live-runner tests."""

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.hyperliquid_protocol import (
    HyperliquidAccountSnapshot,
    HyperliquidPositionSnapshot,
    HyperliquidReconciliationSnapshot,
)


def execution_contract(
    *, maximum_hold_seconds: int = 86_400
) -> ProviderExecutionContract:
    """Return one fixed-stop provider execution contract."""
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=maximum_hold_seconds,
    )


def venue_snapshot(size: float) -> HyperliquidReconciliationSnapshot:
    """Return one deterministic isolated-margin venue snapshot."""
    position = HyperliquidPositionSnapshot(
        size_signed=size,
        entry_price=100.0 if size else None,
        liquidation_price=80.0 if size > 0 else 120.0 if size < 0 else None,
        margin_used_usd=5.0 if size else 0.0,
        position_value_usd=25.0 if size else 0.0,
        unrealized_pnl_usd=0.0,
        leverage_type="isolated" if size else None,
        leverage=5 if size else None,
    )
    account = HyperliquidAccountSnapshot(153.5, 148.0, 5.5, 25.0, position)
    return HyperliquidReconciliationSnapshot(account, (), ())
