"""Coverage of a venue-native fixed-size reduce-only protective stop."""

import math

from hypervector.live.hyperliquid_protocol import HyperliquidOpenOrder

QUANTITY_TOLERANCE = 1e-9


def protective_stop_covers(order: HyperliquidOpenOrder, position_size_signed: float) -> bool:
    """Require correct direction and sufficient reduce-only trigger quantity."""
    expected = abs(position_size_signed)
    return (
        math.isfinite(expected)
        and expected > 0.0
        and math.isfinite(order.size)
        and order.size + QUANTITY_TOLERANCE >= expected
        and order.reduce_only
        and order.is_trigger
        and order.side == ("A" if position_size_signed > 0.0 else "B")
    )
