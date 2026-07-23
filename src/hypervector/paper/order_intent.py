from __future__ import annotations

import time
from typing import Any

ORDER_INTENT_SCHEMA = "hv_order_intent_v1"
NETWORK_MAINNET = "mainnet"


def build_order_intent(
    *,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    time_in_force: str = "ioc",
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
    return {
        "schema": ORDER_INTENT_SCHEMA,
        "network": NETWORK_MAINNET,
        "venue": "hyperliquid",
        "symbol": str(symbol),
        "side": side_n,
        "qty": q,
        "order_type": str(order_type),
        "time_in_force": str(time_in_force),
        "reduce_only": bool(reduce_only),
        "client_ts_ms": ts,
        "submit_enabled": False,  # structural: never true in 4b
        "notes": str(notes),
    }
