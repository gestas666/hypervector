"""Native completed-order size semantics and truthful recovery acknowledgements."""

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, create_autospec

import pytest
from test_native_replay_adapter import ADDRESS, deny_external_ports

from hypervector.live.apex_mm_live_orders import (
    recovered_cancel_ack,
    recovered_order_ack,
)
from hypervector.live.hulk_smash_live_orders import _cancel_status_ack, _status_ack
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
)
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    parse_cancel_ack,
    parse_order_status,
)
from hypervector.live.sol_order_submission import SolOrderSubmission

__all__ = ["deny_external_ports"]
FIXTURE = Path(__file__).parent / "fixtures/native_sndk_order_status_20260913.json"


def response(kind: str = "filled") -> dict[str, object]:
    """Read an authenticated real response without printing account identifiers."""
    return json.loads(FIXTURE.read_text())[kind]["response"]


@pytest.mark.parametrize("kind,remaining", [("filled", 0.0), ("open", 0.306)])
def test_native_order_status_keeps_remaining_and_original_size(kind: str, remaining: float) -> None:
    """A completed order's zero remaining size is valid venue evidence."""
    raw = response(kind)
    order = raw["order"]["order"]
    parsed = parse_order_status(raw, expected_oid=order["oid"])
    assert parsed.size == remaining and parsed.original_size == 0.306
    assert parsed.status == kind and parsed.symbol == "xyz:SNDK"
    assert parse_order_status(raw, expected_client_order_id=order["cloid"]) == parsed


def test_actual_adapter_recovers_native_completed_order_without_inventing_fill_size() -> None:
    """Exact client lookup accepts native zero remaining; fills/position own executed size."""
    info = create_autospec(HyperliquidInfoProtocol, instance=True, spec_set=True)
    exchange = create_autospec(HyperliquidExchangeProtocol, instance=True, spec_set=True)
    info.query_order_by_oid.return_value = raw = response()
    client_id = raw["order"]["order"]["cloid"]
    adapter = BtcHyperliquidAdapter(
        info=info,
        exchange=exchange,
        account_address=ADDRESS,
        max_notional_usd=500,
        slippage_fraction=0.01,
        symbol="xyz:SNDK",
        perp_dex="xyz",
    )
    orders = SolOrderSubmission(
        adapter=adapter, events=Mock(), client_order_id_fn=lambda: client_id
    )
    ack = orders.recover_existing_intent(operation="entry", client_order_id=client_id)
    assert ack.accepted and ack.recovered_after_restart and ack.status == "filled"
    assert ack.oid == raw["order"]["order"]["oid"] and ack.client_order_id == client_id
    assert ack.filled_size is None
    assert not exchange.mock_calls


@pytest.mark.parametrize(
    "helper",
    [
        recovered_order_ack,
        recovered_cancel_ack,
        _status_ack,
        _cancel_status_ack,
        SolOrderSubmission._status_ack,
    ],
)
def test_status_converters_do_not_report_remaining_quantity_as_executed(
    helper: Callable[[HyperliquidOrderStatus], HyperliquidOrderAck],
) -> None:
    """Order status alone supplies no authenticated fill total, even with nonzero sz."""
    status = HyperliquidOrderStatus(7, "BTC", "filled", 0.19, 1000)
    ack = helper(status)
    assert ack.accepted and ack.filled_size is None


def test_sol_cancel_recovery_does_not_report_remaining_size_as_filled() -> None:
    """The cancel race retains terminal status without manufacturing fill telemetry."""
    adapter = Mock()
    adapter.order_status.return_value = HyperliquidOrderStatus(7, "BTC", "filled", 0.19, 1000)
    orders = SolOrderSubmission(adapter=adapter, events=Mock(), client_order_id_fn=lambda: "unused")
    ack = orders._recover_cancel_ack(7)
    assert ack.status == "filled" and ack.filled_size is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("sz", "-0.1"),
        ("sz", "NaN"),
        ("origSz", "0"),
        ("origSz", "-1"),
        ("origSz", "Infinity"),
        ("origSz", True),
    ],
)
def test_invalid_native_quantities_remain_explicit_failures(field: str, value: object) -> None:
    """Accept zero remaining without accepting malformed original quantities."""
    raw = deepcopy(response())
    raw["order"]["order"][field] = value
    with pytest.raises(HyperliquidAdapterError):
        parse_order_status(raw, expected_oid=raw["order"]["order"]["oid"])


def test_legacy_missing_original_size_remains_explicitly_unavailable() -> None:
    """Older responses remain readable without inferring an original or executed size."""
    raw = response()
    del raw["order"]["order"]["origSz"]
    parsed = parse_order_status(raw, expected_oid=raw["order"]["order"]["oid"])
    assert parsed.size == 0 and parsed.original_size is None


@pytest.mark.parametrize("remaining,status", [("0.307", "filled"), ("0", "open")])
def test_inconsistent_size_or_empty_open_order_is_rejected(remaining: str, status: str) -> None:
    """A malformed status cannot claim more remaining than original or zero open size."""
    raw = response()
    raw["order"]["order"]["sz"], raw["order"]["status"] = remaining, status
    with pytest.raises(HyperliquidAdapterError):
        parse_order_status(raw, expected_oid=raw["order"]["order"]["oid"])


@pytest.mark.parametrize("mode", ["no_identity", "two_identities", "wrong_oid", "wrong_status"])
def test_status_identity_and_envelope_validation_remain_strict(mode: str) -> None:
    """Zero-size support does not weaken identity or response-envelope checks."""
    raw = response()
    oid = raw["order"]["order"]["oid"]
    kwargs = {"expected_oid": oid}
    if mode == "no_identity":
        kwargs = {}
    elif mode == "two_identities":
        kwargs["expected_client_order_id"] = raw["order"]["order"]["cloid"]
    elif mode == "wrong_oid":
        kwargs["expected_oid"] = oid + 1
    else:
        raw["status"] = "unrecognized"
    with pytest.raises(HyperliquidAdapterError):
        parse_order_status(raw, **kwargs)


@pytest.mark.parametrize("status", [{"error": "cancel rejected"}, "unexpected", {"unknown": 1}])
def test_cancel_receipt_retains_rejection_and_refuses_unknown_shapes(status: object) -> None:
    """Malformed cancellation cannot be represented as a successful cancellation."""
    raw = {"status": "ok", "response": {"type": "cancel", "data": {"statuses": [status]}}}
    if isinstance(status, dict) and "error" in status:
        ack = parse_cancel_ack(raw, 7)
        assert not ack.accepted and ack.error == "cancel rejected"
    else:
        with pytest.raises(HyperliquidAdapterError):
            parse_cancel_ack(raw, 7)


def test_top_level_cancel_error_is_preserved() -> None:
    """An explicit server rejection remains an error acknowledgement."""
    ack = parse_cancel_ack({"status": "err", "response": "request rejected"}, 7)
    assert not ack.accepted and ack.error == "request rejected"
