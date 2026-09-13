"""Pure order-race decisions for the Apex MM live lifecycle."""

from hypervector.live.apex_mm_live_orders import recovered_cancel_ack
from hypervector.live.hyperliquid_protocol import HyperliquidOrderStatus


def _status(value: str) -> HyperliquidOrderStatus:
    return HyperliquidOrderStatus(7, "BTC", value, 0.00019, 1_785_586_383_357)


def test_cancel_race_accepts_exact_filled_or_canceled_terminal_status() -> None:
    filled = recovered_cancel_ack(_status("filled"))
    canceled = recovered_cancel_ack(_status("canceled"))

    assert filled.accepted is True
    assert filled.status == "filled"
    assert filled.filled_size is None
    assert canceled.accepted is True
    assert canceled.status == "canceled"


def test_cancel_race_rejects_order_that_remains_open() -> None:
    observed = recovered_cancel_ack(_status("open"))

    assert observed.accepted is False
    assert observed.status == "open"
    assert observed.error == "open"
