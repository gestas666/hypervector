from hypervector.paper.order_intent import (
    ORDER_INTENT_SCHEMA,
    NETWORK_MAINNET,
    build_order_intent,
)


def test_build_order_intent_market_shadow():
    d = build_order_intent(symbol="BTC-PERP", side="sell", qty=0.01)
    assert d["schema"] == ORDER_INTENT_SCHEMA
    assert d["network"] == NETWORK_MAINNET
    assert d["venue"] == "hyperliquid"
    assert d["symbol"] == "BTC-PERP"
    assert d["side"] == "sell"
    assert d["qty"] == 0.01
    assert d["order_type"] == "market"
    assert d["time_in_force"] == "ioc"
    assert d["reduce_only"] is False
    assert d["submit_enabled"] is False
    assert "client_ts_ms" in d
    assert d["notes"]


def test_build_order_intent_qty_positive():
    import pytest

    with pytest.raises(ValueError):
        build_order_intent(symbol="ETH-PERP", side="buy", qty=0.0)
