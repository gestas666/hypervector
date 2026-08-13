"""Offline contract tests for durable Hyperliquid client-order identity."""

from __future__ import annotations

import re
from unittest.mock import Mock

import pytest
from requests import Timeout

from hypervector.live.hyperliquid_sol_adapter import SolHyperliquidAdapter
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError


_CLIENT_ORDER_ID = "0x0123456789abcdef0123456789abcdef"


def _adapter() -> tuple[SolHyperliquidAdapter, Mock]:
    info = Mock()
    info.meta.return_value = {
        "universe": [{"name": "SOL", "szDecimals": 2, "maxLeverage": 20}]
    }
    exchange = Mock()
    exchange.market_open.return_value = _filled_response(101)
    exchange.order.return_value = _resting_response(202)
    exchange.market_close.return_value = _filled_response(303)
    return (
        SolHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address="0x1111111111111111111111111111111111111111",
            max_notional_usd=22.50,
            slippage_fraction=0.01,
        ),
        exchange,
    )


def _filled_response(oid: int) -> dict[str, object]:
    return {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {
                "statuses": [
                    {"filled": {"oid": oid, "totalSz": "0.30", "avgPx": "73.10"}}
                ]
            },
        },
    }


def _resting_response(oid: int) -> dict[str, object]:
    return {
        "status": "ok",
        "response": {
            "type": "order",
            "data": {"statuses": [{"resting": {"oid": oid}}]},
        },
    }


def test_new_client_order_id_is_exactly_sixteen_random_bytes() -> None:
    """Each generated ID satisfies Hyperliquid's exact CLOID wire contract."""
    from hypervector.live.sol_order_identity import new_client_order_id

    first = new_client_order_id()
    second = new_client_order_id()

    assert re.fullmatch(r"0x[0-9a-f]{32}", first)
    assert re.fullmatch(r"0x[0-9a-f]{32}", second)
    assert first != second


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0123456789abcdef0123456789abcdef",
        "0x0123",
        "0x0123456789abcdef0123456789abcdeg",
        "0X0123456789abcdef0123456789abcdef",
    ],
)
def test_invalid_client_order_id_is_rejected(value: str) -> None:
    """Malformed identities fail before any authenticated venue call."""
    from hypervector.live.sol_order_identity import (
        SolClientOrderIdError,
        validate_client_order_id,
    )

    with pytest.raises(SolClientOrderIdError, match="client order id"):
        validate_client_order_id(value)


def test_entry_passes_exact_client_order_id_to_official_sdk() -> None:
    """The durable entry identity reaches the authenticated SDK mutation."""
    adapter, exchange = _adapter()

    ack = adapter.submit_entry(
        side="long",
        requested_notional_usd=22.50,
        mark_price=73.0,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.client_order_id == _CLIENT_ORDER_ID
    assert str(exchange.market_open.call_args.kwargs["cloid"]) == _CLIENT_ORDER_ID


def test_stop_passes_exact_client_order_id_to_official_sdk() -> None:
    """The protective stop has an independently recoverable durable identity."""
    adapter, exchange = _adapter()

    ack = adapter.place_protective_stop(
        position_size_signed=0.30,
        trigger_price=72.40,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.client_order_id == _CLIENT_ORDER_ID
    assert str(exchange.order.call_args.kwargs["cloid"]) == _CLIENT_ORDER_ID


def test_close_passes_exact_client_order_id_to_official_sdk() -> None:
    """The reduce-only close can be queried after an ambiguous HTTP response."""
    adapter, exchange = _adapter()

    ack = adapter.close_position(
        position_size_signed=0.30,
        mark_price=73.0,
        client_order_id=_CLIENT_ORDER_ID,
    )

    assert ack.client_order_id == _CLIENT_ORDER_ID
    assert str(exchange.market_close.call_args.kwargs["cloid"]) == _CLIENT_ORDER_ID


def test_order_status_is_reconciled_by_exact_client_order_id() -> None:
    """A lost mutation response can be resolved using only its durable identity."""
    adapter, _ = _adapter()
    info = adapter._info  # noqa: SLF001 - boundary call identity is the contract here.
    info.query_order_by_oid.return_value = _order_status_response(_CLIENT_ORDER_ID)

    status = adapter.order_status_by_client_id(_CLIENT_ORDER_ID)

    assert status.oid == 101
    assert status.client_order_id == _CLIENT_ORDER_ID
    info.query_order_by_oid.assert_called_once_with(
        "0x1111111111111111111111111111111111111111",
        _CLIENT_ORDER_ID,
    )


def test_order_status_rejects_a_different_returned_client_order_id() -> None:
    """A status response for another order cannot be adopted as owned exposure."""
    adapter, _ = _adapter()
    info = adapter._info  # noqa: SLF001 - boundary call identity is the contract here.
    different = "0xffffffffffffffffffffffffffffffff"
    info.query_order_by_oid.return_value = _order_status_response(different)

    with pytest.raises(HyperliquidAdapterError, match="client order id mismatch"):
        adapter.order_status_by_client_id(_CLIENT_ORDER_ID)


def _order_status_response(client_order_id: str) -> dict[str, object]:
    return {
        "status": "order",
        "order": {
            "order": {
                "coin": "SOL",
                "oid": 101,
                "cloid": client_order_id,
                "sz": "0.30",
            },
            "status": "filled",
            "statusTimestamp": 1_785_495_600_123,
        },
    }


def test_entry_timeout_preserves_ambiguous_client_order_identity() -> None:
    """A response timeout is raised with the exact potentially committed CLOID."""
    from hypervector.live.sol_order_transport import SolOrderTransportError

    adapter, exchange = _adapter()
    exchange.market_open.side_effect = Timeout("response deadline exceeded")

    with pytest.raises(SolOrderTransportError) as raised:
        adapter.submit_entry(
            side="long",
            requested_notional_usd=22.50,
            mark_price=73.0,
            client_order_id=_CLIENT_ORDER_ID,
        )

    assert raised.value.operation == "entry"
    assert raised.value.client_order_id == _CLIENT_ORDER_ID
    assert raised.value.ambiguous is True
