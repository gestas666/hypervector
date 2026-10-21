"""Auditable no-submit order intents recorded beside paper/shadow fills."""

from __future__ import annotations

import time
from typing import Any

from hypervector.strategies.registry import execution_profile

ORDER_INTENT_SCHEMA = "hv_order_intent_v1"
NETWORK_MAINNET = "mainnet"


def build_order_intent(
    *,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    time_in_force: str = "ioc",
    limit_px: float | None = None,
    reduce_only: bool = False,
    client_ts_ms: float | None = None,
    notes: str = "shadow-only; not sent",
) -> dict[str, Any]:
    q = float(qty)
    if q <= 0:
        raise ValueError(f"qty must be positive, got {qty!r}")
    side_n = str(side).lower().strip()
    if side_n not in ("buy", "sell"):
        raise ValueError(f"side must be buy|sell, got {side!r}")
    ts = float(client_ts_ms) if client_ts_ms is not None else time.time() * 1000.0
    price = float(limit_px) if limit_px is not None else None
    if price is not None and price <= 0.0:
        raise ValueError(f"limit_px must be positive, got {limit_px!r}")
    return {
        "schema": ORDER_INTENT_SCHEMA,
        "network": NETWORK_MAINNET,
        "venue": "hyperliquid",
        "symbol": str(symbol),
        "side": side_n,
        "qty": q,
        "order_type": str(order_type),
        "time_in_force": str(time_in_force),
        "limit_px": price,
        "reduce_only": bool(reduce_only),
        "client_ts_ms": ts,
        "submit_enabled": False,  # structural: never true in 4b
        "notes": str(notes),
    }


def shadow_order_intent(
    *,
    symbol: str,
    strategy_name: str,
    side: str,
    qty: float,
    mark_px: float,
    action: str,
) -> dict[str, Any]:
    """Build the auditable no-submit intent for one shadow accounting action.

    Entries of a strategy that declares post-only entries are recorded as
    limit post-only orders at ``mark_px``; every other action is market IOC.
    """
    if action == "backstop_liquidation":
        return build_order_intent(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="backstop_transfer",
            time_in_force="transfer",
            reduce_only=True,
            notes="shadow isolated-margin backstop transfer; not sent",
        )
    if action in {"liquidation", "partial_liquidation"}:
        return build_order_intent(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="market",
            time_in_force="ioc",
            reduce_only=True,
            notes="venue-enforced shadow liquidation; not sent",
        )
    reduce_only = action == "close"
    post_only_entry = (
        action in {"enter_long", "enter_short"}
        and execution_profile(strategy_name).post_only_entries
    )
    if not post_only_entry:
        return build_order_intent(
            symbol=symbol,
            side=side,
            qty=qty,
            reduce_only=reduce_only,
        )
    return build_order_intent(
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="limit",
        time_in_force="post_only",
        limit_px=mark_px,
        reduce_only=False,
        notes="shadow post-only intent; not sent",
    )
