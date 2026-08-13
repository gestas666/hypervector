"""Low-REST venue facade for the one-second Apex MM live loop."""

from __future__ import annotations

from collections.abc import Callable
import math
import time
from typing import Protocol

from hypervector.live.apex_mm_venue_stream import (
    ApexMMVenueStreamError,
    ApexMMVenueStreamSnapshot,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    HyperliquidPostOnlyOrder,
    SolBookSnapshot,
    SolFundingPayment,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)


class ApexMMStreamingVenueError(RuntimeError):
    """Streamed and authoritative venue state cannot be reconciled safely."""


_MAX_DEGRADED_RECONCILES = 3
_REST_RETRY_SECONDS = 0.1


class ApexMMVenueStreamProtocol(Protocol):
    """Fresh stream operations used by the REST facade."""

    def start(self, *, timeout_seconds: float) -> None: ...

    def snapshot(self, *, maximum_age_ms: int) -> ApexMMVenueStreamSnapshot: ...

    def state_snapshot(self) -> ApexMMVenueStreamSnapshot: ...

    def wait_for_open_orders(
        self,
        *,
        expected_oids: frozenset[int],
        timeout_seconds: float,
        maximum_age_ms: int,
    ) -> ApexMMVenueStreamSnapshot: ...

    def wait_for_fill(
        self,
        *,
        oid: int,
        timeout_seconds: float,
        markout_horizon_ms: int = 0,
    ) -> ApexMMVenueStreamSnapshot: ...

    def close(self) -> None: ...


class ApexMMRestVenueProtocol(Protocol):
    """Authenticated REST mutations and bounded truth checks."""

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight: ...

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot: ...

    def configure_isolated_leverage(self, leverage: int) -> None: ...

    def reconcile(self) -> SolReconciliationSnapshot: ...

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]: ...

    def cancel_order(self, oid: int) -> HyperliquidOrderAck: ...

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck: ...

    def order_status(self, oid: int) -> HyperliquidOrderStatus: ...

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus: ...

    def funding_payments(
        self,
        **kwargs: int,
    ) -> tuple[SolFundingPayment, ...]: ...


StreamFactory = Callable[[str], ApexMMVenueStreamProtocol]


class ApexMMStreamingVenue:
    """Use WebSocket state per tick and REST only for mutations and audits."""

    def __init__(
        self,
        *,
        delegate: ApexMMRestVenueProtocol,
        stream_factory: StreamFactory,
        maximum_book_age_ms: int,
        confirmation_timeout_seconds: float,
        authoritative_reconcile_seconds: float,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if maximum_book_age_ms < 0:
            raise ValueError("maximum_book_age_ms must be non-negative")
        _require_positive(confirmation_timeout_seconds, "confirmation timeout")
        _require_positive(authoritative_reconcile_seconds, "reconcile interval")
        self._delegate = delegate
        self._stream_factory = stream_factory
        self._maximum_book_age_ms = maximum_book_age_ms
        self._confirmation_timeout_seconds = confirmation_timeout_seconds
        self._authoritative_reconcile_seconds = authoritative_reconcile_seconds
        self._monotonic_fn = monotonic_fn
        self._sleep_fn = sleep_fn
        self._stream: ApexMMVenueStreamProtocol | None = None
        self._expected_oids: set[int] = set()
        self._confirmation_pending = False
        self._order_stream_degraded = False
        self._degraded_reconciles = 0
        self._next_authoritative_at = 0.0
        self._shutdown_mode = False

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        """Run REST preflight, then require a complete streamed snapshot."""
        if self._stream is not None:
            raise ApexMMStreamingVenueError("venue stream already initialized")
        preflight = self._delegate.preflight(
            expected_max_leverage=expected_max_leverage
        )
        stream = self._stream_factory(preflight.account_abstraction_mode)
        try:
            stream.start(timeout_seconds=self._confirmation_timeout_seconds)
            initial = stream.state_snapshot()
        except Exception:
            stream.close()
            raise
        self._stream = stream
        self._expected_oids = {order.oid for order in initial.venue.open_orders}
        self._next_authoritative_at = (
            self._monotonic_fn() + self._authoritative_reconcile_seconds
        )
        return preflight

    def reconcile(self) -> SolReconciliationSnapshot:
        """Return streamed state, periodically challenged against REST truth."""
        if self._shutdown_mode:
            return self._delegate.reconcile()
        stream = self._require_stream()
        if self._order_stream_degraded:
            return self._reconcile_degraded_stream(stream)
        confirmation_pending = self._confirmation_pending
        try:
            streamed = (
                stream.wait_for_open_orders(
                    expected_oids=frozenset(self._expected_oids),
                    timeout_seconds=self._confirmation_timeout_seconds,
                    maximum_age_ms=self._maximum_book_age_ms,
                )
                if self._confirmation_pending
                else stream.state_snapshot()
            )
        except ApexMMVenueStreamError as exc:
            if self._confirmation_pending:
                return self._confirm_mutation_with_rest(exc)
            raise ApexMMStreamingVenueError(str(exc)) from exc
        self._confirmation_pending = False
        if not confirmation_pending:
            self._expected_oids = {order.oid for order in streamed.venue.open_orders}
        if self._monotonic_fn() < self._next_authoritative_at:
            return streamed.venue
        authoritative = self._delegate.reconcile()
        self._require_no_drift(streamed.venue, authoritative)
        self._next_authoritative_at = (
            self._monotonic_fn() + self._authoritative_reconcile_seconds
        )
        return authoritative

    def _confirm_mutation_with_rest(
        self,
        stream_error: ApexMMVenueStreamError,
    ) -> SolReconciliationSnapshot:
        authoritative = self._delegate.reconcile()
        observed = {order.oid for order in authoritative.open_orders}
        if observed != self._expected_oids:
            raise ApexMMStreamingVenueError(
                "REST confirmation mismatch after venue stream timeout"
            ) from stream_error
        self._confirmation_pending = False
        self._order_stream_degraded = True
        self._degraded_reconciles = 0
        return authoritative

    def _reconcile_degraded_stream(
        self,
        stream: ApexMMVenueStreamProtocol,
    ) -> SolReconciliationSnapshot:
        authoritative = self._delegate.reconcile()
        try:
            streamed = stream.state_snapshot().venue
            self._require_no_drift(streamed, authoritative)
        except (ApexMMVenueStreamError, ApexMMStreamingVenueError) as exc:
            self._degraded_reconciles += 1
            if self._degraded_reconciles >= _MAX_DEGRADED_RECONCILES:
                raise ApexMMStreamingVenueError(
                    "venue order stream did not recover after REST confirmation"
                ) from exc
            return authoritative
        self._order_stream_degraded = False
        self._degraded_reconciles = 0
        self._next_authoritative_at = (
            self._monotonic_fn() + self._authoritative_reconcile_seconds
        )
        return authoritative

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        """Return streamed L2 unless shutdown explicitly selects REST truth."""
        if depth_levels <= 0:
            raise ValueError("depth_levels must be positive")
        return self._delegate.book_snapshot(depth_levels=depth_levels)

    def configure_isolated_leverage(self, leverage: int) -> None:
        """Forward the explicit isolated-leverage mutation."""
        self._delegate.configure_isolated_leverage(leverage)

    def submit_entry(self, **kwargs: object) -> HyperliquidOrderAck:
        """Submit one quote leg and require its identity on next reconcile."""
        acknowledgement = self._delegate.submit_entry(**kwargs)
        if acknowledgement.accepted and acknowledgement.oid is not None:
            self._expected_oids.add(acknowledgement.oid)
            self._confirmation_pending = True
        return acknowledgement

    def submit_post_only_batch(
        self,
        orders: tuple[HyperliquidPostOnlyOrder, ...],
    ) -> tuple[HyperliquidOrderAck, ...]:
        """Submit a quote batch and register all accepted identities together."""
        acknowledgements = self._delegate.submit_post_only_batch(orders)
        accepted = {
            acknowledgement.oid
            for acknowledgement in acknowledgements
            if acknowledgement.accepted and acknowledgement.oid is not None
        }
        if accepted:
            self._expected_oids.update(accepted)
            self._confirmation_pending = True
        return acknowledgements

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Cancel one quote and require its absence on next reconcile."""
        acknowledgement = self._delegate.cancel_order(oid)
        if acknowledgement.accepted:
            self._expected_oids.discard(oid)
            self._confirmation_pending = True
        return acknowledgement

    def close_position(self, **kwargs: object) -> HyperliquidOrderAck:
        """Forward the emergency reduce-only close mutation."""
        return self._delegate.close_position(**kwargs)

    def wait_for_fill(
        self,
        oid: int,
        markout_horizon_ms: int,
    ) -> tuple[SolReconciliationSnapshot, SolBookSnapshot]:
        """Require cleanup fill and due markout book from stream or REST."""
        stream = self._require_stream()
        try:
            snapshot = stream.wait_for_fill(
                oid=oid,
                timeout_seconds=self._confirmation_timeout_seconds,
                markout_horizon_ms=markout_horizon_ms,
            )
            return snapshot.venue, snapshot.book
        except ApexMMVenueStreamError as exc:
            confirmed = self._wait_for_rest_fill_markout(oid, markout_horizon_ms)
            if confirmed is not None:
                return confirmed
            raise ApexMMStreamingVenueError(
                f"cleanup fill/markout confirmation timed out for oid {oid}"
            ) from exc

    def _wait_for_rest_fill_markout(
        self,
        oid: int,
        markout_horizon_ms: int,
    ) -> tuple[SolReconciliationSnapshot, SolBookSnapshot] | None:
        deadline = self._monotonic_fn() + self._confirmation_timeout_seconds
        while True:
            venue = self._delegate.reconcile()
            fill = next((item for item in venue.fills if item.oid == oid), None)
            if fill is not None:
                book = self._delegate.book_snapshot(depth_levels=1)
                if book.exchange_timestamp_ms >= fill.timestamp_ms + markout_horizon_ms:
                    return venue, book
            remaining = deadline - self._monotonic_fn()
            if remaining <= 0.0:
                return None
            self._sleep_fn(min(_REST_RETRY_SECONDS, remaining))

    def order_status(self, oid: int) -> HyperliquidOrderStatus:
        """Recover one ambiguous mutation and synchronize terminal identity."""
        status = self._delegate.order_status(oid)
        if status.oid != oid:
            raise ApexMMStreamingVenueError(
                f"order-status identity mismatch: requested {oid}, received {status.oid}"
            )
        if status.status in {"filled", "canceled"}:
            self._expected_oids.discard(oid)
            self._confirmation_pending = True
        return status

    def order_status_by_client_id(
        self,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        """Recover one ambiguous mutation and synchronize its streamed identity."""
        status = self._delegate.order_status_by_client_id(client_order_id)
        if status.status == "open":
            self._expected_oids.add(status.oid)
        else:
            self._expected_oids.discard(status.oid)
        self._confirmation_pending = True
        return status

    def funding_payments(
        self,
        **kwargs: int,
    ) -> tuple[SolFundingPayment, ...]:
        """Read exact funding rows through the bounded REST endpoint."""
        return self._delegate.funding_payments(**kwargs)

    def begin_shutdown(self) -> None:
        """Select authoritative REST state for cleanup after any stream fault."""
        self._shutdown_mode = True

    def close(self) -> None:
        """Close the private stream without issuing venue mutations."""
        stream = self._stream
        if stream is not None:
            stream.close()
            self._stream = None

    def _require_stream(self) -> ApexMMVenueStreamProtocol:
        if self._stream is None:
            raise ApexMMStreamingVenueError("venue stream is not initialized")
        return self._stream

    @staticmethod
    def _require_no_drift(
        streamed: SolReconciliationSnapshot,
        authoritative: SolReconciliationSnapshot,
    ) -> None:
        streamed_oids = {order.oid for order in streamed.open_orders}
        authoritative_oids = {order.oid for order in authoritative.open_orders}
        position_delta = (
            streamed.position.size_signed - authoritative.position.size_signed
        )
        if streamed_oids != authoritative_oids or abs(position_delta) > 1e-12:
            raise ApexMMStreamingVenueError(
                "stream/REST drift detected for position or open orders"
            )


def _require_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
