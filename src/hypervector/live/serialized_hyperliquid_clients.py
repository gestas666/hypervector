"""One re-entrant serialization boundary for shared Hyperliquid SDK clients."""

from __future__ import annotations

from collections.abc import Callable
import math
from threading import RLock
import time

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.hyperliquid_protocol import (
    HyperliquidExchangeProtocol,
    HyperliquidInfoProtocol,
)

_DEFAULT_READ_RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)


class _ReadCoalescer:
    """Bound duplicate account reads while preserving timed refreshes."""

    def __init__(
        self,
        window_seconds: float,
        monotonic_fn: Callable[[], float],
    ) -> None:
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or not math.isfinite(window_seconds)
            or window_seconds < 0.0
        ):
            raise ValueError("read coalesce window must be finite and nonnegative")
        self._window_seconds = float(window_seconds)
        self._monotonic_fn = monotonic_fn
        self._entries: dict[tuple[object, ...], tuple[float, object]] = {}

    def read(
        self,
        key: tuple[object, ...],
        loader: Callable[[], object],
    ) -> object:
        """Return a still-current shared response or load venue truth."""
        now = self._now()
        cached = self._entries.get(key)
        if cached is not None and now < cached[0]:
            return cached[1]
        value = loader()
        self._entries[key] = (now + self._window_seconds, value)
        return value

    def invalidate(self) -> None:
        """Discard every response before a signed account mutation."""
        self._entries.clear()

    def _now(self) -> float:
        value = self._monotonic_fn()
        if not math.isfinite(value):
            raise ValueError("monotonic clock must return a finite value")
        return value


class SerializedHyperliquidInfo:
    """Serialize every read through the cohort's shared SDK lock."""

    def __init__(
        self,
        delegate: HyperliquidInfoProtocol,
        lock: RLock,
        coalescer: _ReadCoalescer | None = None,
        read_retry_backoff_seconds: tuple[
            float, ...
        ] = _DEFAULT_READ_RETRY_BACKOFF_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._delegate = delegate
        self._lock = lock
        self._coalescer = coalescer
        self._read_retry_backoff_seconds = _validated_backoffs(
            read_retry_backoff_seconds
        )
        self._sleep_fn = sleep_fn

    def meta(self, dex: str = "") -> object:
        """Return perpetual metadata under shared serialization."""
        return self._read(lambda: self._delegate.meta(dex))

    def perp_dexs(self) -> object:
        """Return HIP-3 deployer metadata under shared serialization."""
        return self._read(self._delegate.perp_dexs)

    def user_fees(self, address: str) -> object:
        """Return account fees under shared serialization."""
        return self._read(lambda: self._delegate.user_fees(address))

    def all_mids(self, dex: str = "") -> object:
        """Return current mids under shared serialization."""
        return self._read(lambda: self._delegate.all_mids(dex))

    def l2_snapshot(self, name: str) -> object:
        """Return one order book under shared serialization."""
        return self._read(lambda: self._delegate.l2_snapshot(name))

    def user_state(self, address: str, dex: str = "") -> object:
        """Return clearinghouse state under shared serialization."""
        return self._shared_read(
            ("user_state", address, dex),
            lambda: self._delegate.user_state(address, dex),
        )

    def query_user_abstraction_state(self, address: str) -> object:
        """Return account mode under shared serialization."""
        return self._shared_read(
            ("query_user_abstraction_state", address),
            lambda: self._delegate.query_user_abstraction_state(address),
        )

    def spot_user_state(self, address: str) -> object:
        """Return spot state under shared serialization."""
        return self._shared_read(
            ("spot_user_state", address),
            lambda: self._delegate.spot_user_state(address),
        )

    def user_role(self, address: str) -> object:
        """Return signer role under shared serialization."""
        return self._read(lambda: self._delegate.user_role(address))

    def frontend_open_orders(self, address: str, dex: str = "") -> object:
        """Return open orders under shared serialization."""
        return self._shared_read(
            ("frontend_open_orders", address, dex),
            lambda: self._delegate.frontend_open_orders(address, dex),
        )

    def user_fills(self, address: str) -> object:
        """Return recent fills under shared serialization."""
        return self._shared_read(
            ("user_fills", address),
            lambda: self._delegate.user_fills(address),
        )

    def query_order_by_oid(self, user: str, oid: int | str) -> object:
        """Return one order state under shared serialization."""
        return self._read(lambda: self._delegate.query_order_by_oid(user, oid))

    def user_funding_history(
        self,
        user: str,
        startTime: int,
        endTime: int | None = None,
    ) -> object:
        """Return funding history under shared serialization."""
        return self._shared_read(
            ("user_funding_history", user, startTime, endTime),
            lambda: self._delegate.user_funding_history(
                user,
                startTime=startTime,
                endTime=endTime,
            ),
        )

    def invalidate_shared_reads(self) -> None:
        """Discard coalesced account truth before a consistency retry."""
        with self._lock:
            if self._coalescer is not None:
                self._coalescer.invalidate()

    def _shared_read(
        self,
        key: tuple[object, ...],
        loader: Callable[[], object],
    ) -> object:
        with self._lock:
            if self._coalescer is None:
                return self._retry_read(loader)
            return self._coalescer.read(key, lambda: self._retry_read(loader))

    def _read(self, loader: Callable[[], object]) -> object:
        with self._lock:
            return self._retry_read(loader)

    def _retry_read(self, loader: Callable[[], object]) -> object:
        attempts = len(self._read_retry_backoff_seconds) + 1
        for attempt in range(attempts):
            try:
                return loader()
            except (RequestException, ClientError, ServerError) as exc:
                exhausted = attempt == attempts - 1
                if exhausted or not _retryable_read_error(exc):
                    raise
                self._sleep_fn(self._read_retry_backoff_seconds[attempt])
        raise AssertionError("venue read retry exhausted without returning")


class SerializedHyperliquidExchange:
    """Serialize every signed mutation through the same SDK lock as reads."""

    def __init__(
        self,
        delegate: HyperliquidExchangeProtocol,
        lock: RLock,
        coalescer: _ReadCoalescer | None = None,
    ) -> None:
        self._delegate = delegate
        self._lock = lock
        self._coalescer = coalescer

    def update_leverage(
        self,
        leverage: int,
        name: str,
        is_cross: bool = True,
    ) -> object:
        """Update symbol leverage under shared serialization."""
        return self._mutate(
            lambda: self._delegate.update_leverage(leverage, name, is_cross)
        )

    def market_open(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit one IOC opening order under shared serialization."""
        return self._mutate(
            lambda: self._delegate.market_open(
                name,
                is_buy,
                sz,
                px=px,
                slippage=slippage,
                cloid=cloid,
                builder=builder,
            )
        )

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: object,
        reduce_only: bool = False,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit one explicit order under shared serialization."""
        return self._mutate(
            lambda: self._delegate.order(
                name,
                is_buy,
                sz,
                limit_px,
                order_type,
                reduce_only=reduce_only,
                cloid=cloid,
                builder=builder,
            )
        )

    def bulk_orders(
        self,
        order_requests: list[object],
        builder: object | None = None,
        grouping: str = "na",
    ) -> object:
        """Submit one order batch under shared serialization."""
        return self._mutate(
            lambda: self._delegate.bulk_orders(
                order_requests,
                builder=builder,
                grouping=grouping,
            )
        )

    def cancel(self, name: str, oid: int) -> object:
        """Cancel one order under shared serialization."""
        return self._mutate(lambda: self._delegate.cancel(name, oid))

    def market_close(
        self,
        coin: str,
        sz: float | None = None,
        px: float | None = None,
        slippage: float = 0.05,
        cloid: object | None = None,
        builder: object | None = None,
    ) -> object:
        """Submit one reduce-only IOC close under shared serialization."""
        return self._mutate(
            lambda: self._delegate.market_close(
                coin,
                sz=sz,
                px=px,
                slippage=slippage,
                cloid=cloid,
                builder=builder,
            )
        )

    def _mutate(self, operation: Callable[[], object]) -> object:
        with self._lock:
            if self._coalescer is not None:
                self._coalescer.invalidate()
            return operation()


def shared_serialized_clients(
    info: HyperliquidInfoProtocol,
    exchange: HyperliquidExchangeProtocol,
    *,
    read_coalesce_seconds: float = 0.0,
    monotonic_fn: Callable[[], float] = time.monotonic,
    read_retry_backoff_seconds: tuple[float, ...] = _DEFAULT_READ_RETRY_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[SerializedHyperliquidInfo, SerializedHyperliquidExchange]:
    """Wrap one SDK pair with one shared re-entrant serialization lock."""
    lock = RLock()
    coalescer = _ReadCoalescer(read_coalesce_seconds, monotonic_fn)
    return (
        SerializedHyperliquidInfo(
            info,
            lock,
            coalescer,
            read_retry_backoff_seconds,
            sleep_fn,
        ),
        SerializedHyperliquidExchange(exchange, lock, coalescer),
    )


def _validated_backoffs(values: tuple[float, ...]) -> tuple[float, ...]:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0.0
        for value in values
    ):
        raise ValueError("read retry backoffs must be finite and nonnegative")
    return tuple(float(value) for value in values)


def _retryable_read_error(exc: Exception) -> bool:
    if isinstance(exc, RequestException):
        return True
    if isinstance(exc, ClientError):
        return exc.status_code == 429
    return isinstance(exc, ServerError) and exc.status_code >= 500
