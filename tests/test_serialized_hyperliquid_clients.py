"""Concurrency tests for one shared Hyperliquid SDK authority."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock, RLock
import time
from unittest.mock import Mock

from hyperliquid.utils.error import ClientError
import pytest
from requests import ReadTimeout

from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)
from hypervector.live.serialized_hyperliquid_clients import (
    SerializedHyperliquidExchange,
    SerializedHyperliquidInfo,
    shared_serialized_clients,
)


class _ConcurrencyProbe:
    """Measure the largest number of simultaneous delegated calls."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.maximum = 0

    def call(self, value: object) -> object:
        """Hold one call briefly so an unsafe peer could overlap it."""
        with self._lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        time.sleep(0.02)
        with self._lock:
            self.active -= 1
        return value


class _Clock:
    """Deterministic monotonic clock for bounded read coalescing."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        """Return the current test time."""
        return self.value

    def advance(self, seconds: float) -> None:
        """Advance the monotonic test time."""
        self.value += seconds


def test_info_and_exchange_share_one_serialization_boundary() -> None:
    """Read and signed calls cannot overlap through the cohort authority."""
    probe = _ConcurrencyProbe()
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.user_state.side_effect = lambda address, dex="": probe.call(
        {"address": address}
    )
    exchange.market_open.side_effect = (
        lambda name,
        is_buy,
        sz,
        px=None,
        slippage=0.05,
        cloid=None,
        builder=None: probe.call({"name": name, "is_buy": is_buy, "size": sz})
    )
    wrapped_info, wrapped_exchange = shared_serialized_clients(info, exchange)

    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(wrapped_info.user_state, "0x1")
        write = pool.submit(wrapped_exchange.market_open, "BTC", False, 0.01)
        assert read.result()["address"] == "0x1"
        assert write.result()["name"] == "BTC"

    assert probe.maximum == 1
    assert isinstance(wrapped_info, SerializedHyperliquidInfo)
    assert isinstance(wrapped_exchange, SerializedHyperliquidExchange)


def test_delegated_exception_is_not_converted_to_success() -> None:
    """Serialization must preserve fail-closed SDK errors exactly."""
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    expected = RuntimeError("venue refused")
    exchange.cancel.side_effect = expected
    _, wrapped_exchange = shared_serialized_clients(info, exchange)

    try:
        wrapped_exchange.cancel("SOL", 7)
    except RuntimeError as observed:
        assert observed is expected
    else:
        raise AssertionError("serialized exchange swallowed a venue error")


def test_shared_account_reads_are_coalesced_only_inside_the_bounded_window() -> None:
    """Four symbol readers can share one account response per cohort cycle."""
    clock = _Clock()
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.user_state.return_value = {"kind": "perp"}
    info.spot_user_state.return_value = {"kind": "spot"}
    info.frontend_open_orders.return_value = []
    info.user_fills.return_value = []
    info.user_funding_history.return_value = []
    wrapped, _ = shared_serialized_clients(
        info,
        exchange,
        read_coalesce_seconds=10.0,
        monotonic_fn=clock,
    )

    for _ in range(4):
        assert wrapped.user_state("0x1") == {"kind": "perp"}
        assert wrapped.spot_user_state("0x1") == {"kind": "spot"}
        assert wrapped.frontend_open_orders("0x1") == []
        assert wrapped.user_fills("0x1") == []
        assert wrapped.user_funding_history("0x1", 100, 200) == []

    assert info.user_state.call_count == 1
    assert info.spot_user_state.call_count == 1
    assert info.frontend_open_orders.call_count == 1
    assert info.user_fills.call_count == 1
    assert info.user_funding_history.call_count == 1
    clock.advance(10.1)
    wrapped.user_state("0x1")
    assert info.user_state.call_count == 2


def test_signed_mutation_invalidates_coalesced_account_truth() -> None:
    """Order mutation cannot be followed by a stale cached reconciliation."""
    clock = _Clock()
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.user_state.side_effect = ({"version": 1}, {"version": 2})
    exchange.market_open.return_value = {"status": "ok"}
    wrapped_info, wrapped_exchange = shared_serialized_clients(
        info,
        exchange,
        read_coalesce_seconds=10.0,
        monotonic_fn=clock,
    )

    assert wrapped_info.user_state("0x1") == {"version": 1}
    assert wrapped_info.user_state("0x1") == {"version": 1}
    wrapped_exchange.market_open("BTC", True, 0.001)

    assert wrapped_info.user_state("0x1") == {"version": 2}
    assert info.user_state.call_count == 2


def test_explicit_consistency_retry_invalidates_coalesced_truth() -> None:
    """Post-write polling can force a fresh read without another mutation."""
    clock = _Clock()
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.frontend_open_orders.side_effect = ([{"oid": 11}], [{"oid": 11}, {"oid": 22}])
    wrapped_info, _ = shared_serialized_clients(
        info,
        exchange,
        read_coalesce_seconds=10.0,
        monotonic_fn=clock,
    )

    assert wrapped_info.frontend_open_orders("0x1") == [{"oid": 11}]
    assert wrapped_info.frontend_open_orders("0x1") == [{"oid": 11}]
    wrapped_info.invalidate_shared_reads()

    assert wrapped_info.frontend_open_orders("0x1") == [
        {"oid": 11},
        {"oid": 22},
    ]
    assert info.frontend_open_orders.call_count == 2


def test_idempotent_info_read_retries_transient_timeout() -> None:
    """A transient account timeout must not terminate live reconciliation."""
    sleeps: list[float] = []
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.spot_user_state.side_effect = (ReadTimeout("deadline"), {"kind": "spot"})
    wrapped, _ = shared_serialized_clients(
        info,
        exchange,
        read_retry_backoff_seconds=(0.25, 0.5),
        sleep_fn=sleeps.append,
    )

    assert wrapped.spot_user_state("0x1") == {"kind": "spot"}
    assert info.spot_user_state.call_count == 2
    assert sleeps == [0.25]


def test_hip3_dex_metadata_read_uses_serialized_retry_boundary() -> None:
    """HIP-3 fee metadata cannot bypass serialization or transient retries."""
    sleeps: list[float] = []
    info = Mock(spec=HyperliquidInfoProtocol)
    info.perp_dexs.side_effect = (ReadTimeout("deadline"), [{"name": "xyz"}])
    wrapped = SerializedHyperliquidInfo(
        info,
        RLock(),
        read_retry_backoff_seconds=(0.25,),
        sleep_fn=sleeps.append,
    )

    assert wrapped.perp_dexs() == [{"name": "xyz"}]
    assert info.perp_dexs.call_count == 2
    assert sleeps == [0.25]


def test_idempotent_info_read_retries_only_rate_limit_client_error() -> None:
    """HTTP 429 is transient, while another client rejection remains fatal."""
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.user_state.side_effect = (
        ClientError(429, None, "limited", {}),
        {"kind": "perp"},
    )
    wrapped, _ = shared_serialized_clients(
        info,
        exchange,
        read_retry_backoff_seconds=(0.0,),
        sleep_fn=lambda _: None,
    )
    assert wrapped.user_state("0x1") == {"kind": "perp"}

    rejected = ClientError(422, None, "rejected", {})
    info.frontend_open_orders.side_effect = rejected
    with pytest.raises(ClientError) as caught:
        wrapped.frontend_open_orders("0x1")
    assert caught.value is rejected
    assert info.frontend_open_orders.call_count == 1


def test_info_read_retry_exhaustion_preserves_last_transport_error() -> None:
    """Bounded retry must still fail explicitly when venue reads remain unavailable."""
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    errors = (ReadTimeout("one"), ReadTimeout("two"), ReadTimeout("three"))
    info.user_fills.side_effect = errors
    wrapped, _ = shared_serialized_clients(
        info,
        exchange,
        read_retry_backoff_seconds=(0.0, 0.0),
        sleep_fn=lambda _: None,
    )

    with pytest.raises(ReadTimeout) as caught:
        wrapped.user_fills("0x1")
    assert caught.value is errors[-1]
    assert info.user_fills.call_count == 3


def test_serialized_exchange_implements_every_exchange_protocol_method() -> None:
    """A protocol method missing from the wrapper fails at the first live call."""
    required = {
        name
        for name, value in vars(HyperliquidExchangeProtocol).items()
        if callable(value) and not name.startswith("_")
    }

    missing = sorted(
        name for name in required if not hasattr(SerializedHyperliquidExchange, name)
    )

    assert "modify_order" in required
    assert missing == []


def test_modify_order_delegates_every_argument_and_invalidates_truth() -> None:
    """The venue stop raise reaches the SDK intact and refreshes account truth."""
    clock = _Clock()
    info = Mock(spec=HyperliquidInfoProtocol)
    exchange = Mock(spec=HyperliquidExchangeProtocol)
    info.user_state.side_effect = ({"version": 1}, {"version": 2})
    exchange.modify_order.return_value = {"status": "ok"}
    wrapped_info, wrapped_exchange = shared_serialized_clients(
        info,
        exchange,
        read_coalesce_seconds=10.0,
        monotonic_fn=clock,
    )
    order_type = {"trigger": {"triggerPx": 99.3, "isMarket": True, "tpsl": "sl"}}

    assert wrapped_info.user_state("0x1") == {"version": 1}
    assert wrapped_exchange.modify_order(
        555018726035,
        "xyz:EEE",
        False,
        5.84,
        99.3,
        order_type,
        reduce_only=True,
        cloid="0xabc",
    ) == {"status": "ok"}

    exchange.modify_order.assert_called_once_with(
        555018726035,
        "xyz:EEE",
        False,
        5.84,
        99.3,
        order_type,
        reduce_only=True,
        cloid="0xabc",
    )
    assert wrapped_info.user_state("0x1") == {"version": 2}
