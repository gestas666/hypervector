"""Persist SOL live order intent before authenticated venue mutation."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Protocol

from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
)
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolLiveAdapterProtocol,
)
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidOrderUnavailableError,
)
from hypervector.live.sol_order_identity import validate_client_order_id
from hypervector.live.sol_execution_evidence import (
    canceled_close_fill_size,
    canceled_close_has_no_observed_fill,
    canceled_entry_fill_size,
)
from hypervector.live.sol_order_transport import (
    SolCancelTransportError,
    SolOrderTransportError,
)


class SolOrderSubmissionError(RuntimeError):
    """A submitted acknowledgement did not match its durable intent."""


class SolOrderRecoveryError(RuntimeError):
    """A response-loss order remained unresolved after bounded exact lookup."""

    def __init__(self, *, operation: str, client_order_id: str) -> None:
        self.operation = operation
        self.client_order_id = validate_client_order_id(client_order_id)
        super().__init__(f"{operation} remains ambiguous after exact client-order lookup")


class SolCancelRecoveryError(RuntimeError):
    """An exact cancel remained unresolved after bounded OID lookup."""

    def __init__(self, *, oid: int) -> None:
        self.oid = _positive_oid(oid)
        super().__init__(f"cancel remains ambiguous after exact oid lookup: {oid}")


class SolOrderEventSink(Protocol):
    """Synchronous durable event boundary required before venue writes."""

    def emit(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Persist one execution event before returning."""
        ...

    def fault(self, reason: str) -> None:
        """Persist and enter a technical fault state."""
        ...


class SolOrderSubmission:
    """Bind one persisted client identity to each authenticated mutation."""

    def __init__(
        self,
        *,
        adapter: SolLiveAdapterProtocol,
        events: SolOrderEventSink,
        client_order_id_fn: Callable[[], str],
        recovery_attempts: int = 4,
        recovery_delay_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if isinstance(recovery_attempts, bool) or recovery_attempts < 1:
            raise ValueError("order recovery attempts must be positive")
        if not math.isfinite(recovery_delay_seconds) or recovery_delay_seconds < 0.0:
            raise ValueError("order recovery delay must be nonnegative and finite")
        self._adapter = adapter
        self._events = events
        self._client_order_id_fn = client_order_id_fn
        self._recovery_attempts = recovery_attempts
        self._recovery_delay_seconds = recovery_delay_seconds
        self._sleep_fn = sleep_fn

    def submit_entry(
        self,
        *,
        side: str,
        requested_notional_usd: float,
        mark_price: float,
        entry_deadline: EntrySubmissionDeadline | None = None,
    ) -> HyperliquidOrderAck:
        """Persist entry identity, submit it, and verify acknowledgement identity."""
        client_order_id = validate_client_order_id(self._client_order_id_fn())
        self._emit_entry_intent(
            client_order_id,
            side,
            requested_notional_usd,
            mark_price,
            entry_deadline,
        )
        try:
            if entry_deadline is not None:
                entry_deadline.check("adapter_dispatch")
            ack = self._adapter.submit_entry(
                side=side,
                requested_notional_usd=requested_notional_usd,
                mark_price=mark_price,
                client_order_id=client_order_id,
                **({"entry_deadline": entry_deadline} if entry_deadline is not None else {}),
            )
        except EntryDeadlineExpired as exc:
            self._events.emit(
                "entry_not_submitted",
                {
                    "operation": "entry",
                    "client_order_id": client_order_id,
                    "submitted": False,
                    "reason": "stale_before_submission",
                    **exc.observation.as_payload(),
                },
            )
            raise
        except SolOrderTransportError as exc:
            ack = self._recover_ack(exc, operation="entry")
        self._require_matching_ack("entry", client_order_id, ack)
        return ack

    def _emit_entry_intent(
        self,
        client_order_id: str,
        side: str,
        notional: float,
        price: float,
        deadline: EntrySubmissionDeadline | None,
    ) -> None:
        payload: dict[str, object] = {
            "operation": "entry",
            "client_order_id": client_order_id,
            "side": side,
            "requested_notional_usd": notional,
            "mark_price": price,
        }
        if deadline is not None:
            payload["entry_deadline"] = {
                "decision_time_ms": deadline.decision_time_ms,
                "limit_ms": deadline.limit_ms,
            }
        self._events.emit("order_intent", payload)

    def place_protective_stop(
        self,
        *,
        position_size_signed: float,
        trigger_price: float,
    ) -> HyperliquidOrderAck:
        """Persist stop identity, submit it, and verify acknowledgement identity."""
        client_order_id = validate_client_order_id(self._client_order_id_fn())
        self._events.emit(
            "order_intent",
            {
                "operation": "protective_stop",
                "client_order_id": client_order_id,
                "position_size_signed": position_size_signed,
                "trigger_price": trigger_price,
            },
        )
        try:
            ack = self._adapter.place_protective_stop(
                position_size_signed=position_size_signed,
                trigger_price=trigger_price,
                client_order_id=client_order_id,
            )
        except SolOrderTransportError as exc:
            ack = self._recover_ack(exc, operation="protective_stop")
        self._require_matching_ack("protective stop", client_order_id, ack)
        return ack

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
    ) -> HyperliquidOrderAck:
        """Persist close identity, submit it, and verify acknowledgement identity."""
        client_order_id = validate_client_order_id(self._client_order_id_fn())
        self._events.emit(
            "order_intent",
            {
                "operation": "reduce_only_close",
                "client_order_id": client_order_id,
                "position_size_signed": position_size_signed,
                "mark_price": mark_price,
            },
        )
        try:
            ack = self._adapter.close_position(
                position_size_signed=position_size_signed,
                mark_price=mark_price,
                client_order_id=client_order_id,
            )
        except SolOrderTransportError as exc:
            ack = self._recover_ack(exc, operation="reduce_only_close")
        self._require_matching_ack("reduce-only close", client_order_id, ack)
        return ack

    def place_target(
        self,
        *,
        position_size_signed: float,
        limit_price: float,
    ) -> HyperliquidOrderAck:
        """Persist target identity, submit it, and verify acknowledgement identity."""
        client_order_id = validate_client_order_id(self._client_order_id_fn())
        self._events.emit(
            "order_intent",
            {
                "operation": "target",
                "client_order_id": client_order_id,
                "position_size_signed": position_size_signed,
                "limit_price": limit_price,
            },
        )
        try:
            ack = self._adapter.submit_target(
                position_size_signed=position_size_signed,
                limit_price=limit_price,
                client_order_id=client_order_id,
            )
        except SolOrderTransportError as exc:
            ack = self._recover_ack(exc, operation="target")
        self._require_matching_ack("target", client_order_id, ack)
        return ack

    def cancel_order(self, oid: int) -> HyperliquidOrderAck:
        """Persist exact cancel intent and recover response loss by original OID."""
        order_id = _positive_oid(oid)
        self._events.emit(
            "cancel_intent",
            {"operation": "cancel_order", "oid": order_id},
        )
        try:
            return self._adapter.cancel_order(order_id)
        except SolCancelTransportError:
            return self._recover_cancel_ack(order_id)

    def recover_existing_intent(
        self,
        *,
        operation: str,
        client_order_id: str,
    ) -> HyperliquidOrderAck:
        """Resolve one durable pre-crash intent without submitting another order."""
        if operation not in {
            "entry",
            "protective_stop",
            "target",
            "reduce_only_close",
        }:
            raise SolOrderSubmissionError(f"unsupported order recovery operation: {operation!r}")
        validated_id = validate_client_order_id(client_order_id)
        status = self._recover_status(operation, validated_id)
        ack = replace(self._confirmed_status_ack(operation, status), recovered_after_restart=True)
        self._require_matching_ack(operation, validated_id, ack)
        return ack

    def recover_existing_cancel(self, oid: int) -> HyperliquidOrderAck:
        """Resolve a committed cancel by its original OID without another mutation."""
        ack = self._recover_cancel_ack(_positive_oid(oid))
        return replace(ack, recovered_after_restart=True)

    @staticmethod
    def _require_matching_ack(
        operation: str,
        client_order_id: str,
        ack: HyperliquidOrderAck,
    ) -> None:
        if ack.client_order_id != client_order_id:
            raise SolOrderSubmissionError(
                f"{operation} acknowledgement client order id does not match durable intent"
            )

    def _recover_ack(
        self, failure: SolOrderTransportError, *, operation: str
    ) -> HyperliquidOrderAck:
        status = self._recover_status(failure.operation, failure.client_order_id)
        return replace(
            self._confirmed_status_ack(operation, status),
            recovered_after_transport_error=True,
        )

    def _confirmed_status_ack(
        self, operation: str, status: HyperliquidOrderStatus
    ) -> HyperliquidOrderAck:
        ack = self._status_ack(status)
        if operation not in {"entry", "reduce_only_close"} or status.status != "canceled":
            return ack
        if operation == "reduce_only_close" and status.original_size is None:
            return ack
        if status.client_order_id is None:
            raise SolOrderSubmissionError("canceled execution status lacks client order identity")
        check = canceled_entry_fill_size if operation == "entry" else canceled_close_fill_size
        for attempt in range(self._recovery_attempts):
            venue = self._adapter.reconcile()
            quantity = check(status, venue)
            if quantity is not None:
                return replace(ack, accepted=True, error=None, filled_size=quantity)
            if venue.is_flat:
                return ack
            if operation == "reduce_only_close" and canceled_close_has_no_observed_fill(
                status, venue
            ):
                return ack
            if attempt + 1 < self._recovery_attempts:
                self._sleep_fn(self._recovery_delay_seconds)
        error = SolOrderRecoveryError(operation=operation, client_order_id=status.client_order_id)
        self._events.fault(f"{error}; client_order_id={status.client_order_id}")
        raise error

    def _recover_status(
        self,
        operation: str,
        client_order_id: str,
    ) -> HyperliquidOrderStatus:
        for attempt in range(self._recovery_attempts):
            try:
                return self._adapter.order_status_by_client_id(client_order_id)
            except HyperliquidOrderUnavailableError as exc:
                if attempt + 1 == self._recovery_attempts:
                    error = SolOrderRecoveryError(
                        operation=operation,
                        client_order_id=client_order_id,
                    )
                    self._events.fault(f"{error}; client_order_id={client_order_id}")
                    raise error from exc
                self._sleep_fn(self._recovery_delay_seconds)
        raise AssertionError("order recovery loop exhausted without returning")

    def _recover_cancel_ack(self, oid: int) -> HyperliquidOrderAck:
        for attempt in range(self._recovery_attempts):
            try:
                status = self._adapter.order_status(oid)
            except HyperliquidOrderUnavailableError as exc:
                if attempt + 1 == self._recovery_attempts:
                    error = SolCancelRecoveryError(oid=oid)
                    self._events.fault(str(error))
                    raise error from exc
                self._sleep_fn(self._recovery_delay_seconds)
                continue
            accepted = status.status == "canceled"
            return HyperliquidOrderAck(
                accepted=accepted,
                oid=status.oid,
                status=status.status,
                error=None if accepted else status.status,
                recovered_after_transport_error=True,
                venue_timestamp_ms=status.status_timestamp_ms,
            )
        raise AssertionError("cancel recovery loop exhausted without returning")

    @staticmethod
    def _status_ack(
        status: HyperliquidOrderStatus,
        *,
        recovered_after_transport_error: bool = False,
        recovered_after_restart: bool = False,
    ) -> HyperliquidOrderAck:
        accepted = status.status in {"filled", "open"}
        return HyperliquidOrderAck(
            accepted=accepted,
            oid=status.oid,
            status=status.status,
            error=None if accepted else status.status,
            client_order_id=status.client_order_id,
            recovered_after_transport_error=recovered_after_transport_error,
            venue_timestamp_ms=status.status_timestamp_ms,
            recovered_after_restart=recovered_after_restart,
        )


def _positive_oid(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("cancel oid must be a positive integer")
    return value
