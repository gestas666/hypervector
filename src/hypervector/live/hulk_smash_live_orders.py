"""Venue order intents and acknowledgements for the Hulk lifecycle."""

from __future__ import annotations

from collections.abc import Callable
import time

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_protocol import HulkSmashVenueProtocol
from hypervector.live.hulk_smash_live_risk import HulkProtectionPlan
from hypervector.live.hulk_smash_live_telemetry import HulkSmashLiveTelemetry
from hypervector.live.hyperliquid_protocol import (
    HyperliquidOrderAck,
    HyperliquidOrderStatus,
    SolReconciliationSnapshot,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidOrderUnavailableError
from hypervector.live.sol_order_identity import validate_client_order_id
from hypervector.live.sol_order_transport import (
    SolCancelTransportError,
    SolOrderTransportError,
)


class HulkSmashOrderError(RuntimeError):
    """A venue rejected one required Hulk order."""


class HulkSmashOrderAmbiguityError(HulkSmashOrderError):
    """Exact status recovery could not resolve a lost mutation response."""

    def __init__(self, operation: str, identity: str) -> None:
        self.operation = operation
        self.identity = identity
        super().__init__(
            f"{operation} remains ambiguous after exact venue-status lookup"
        )


class HulkSmashOrderGateway:
    """Submit exact entry and bracket orders with durable intent telemetry."""

    def __init__(
        self,
        *,
        adapter: HulkSmashVenueProtocol,
        telemetry: HulkSmashLiveTelemetry,
        client_order_id_fn: Callable[[], str],
        recovery_attempts: int = 4,
        recovery_delay_seconds: float = 0.25,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if recovery_attempts < 1 or recovery_delay_seconds < 0.0:
            raise ValueError("invalid Hulk order recovery policy")
        self._adapter = adapter
        self._telemetry = telemetry
        self._client_order_id_fn = client_order_id_fn
        self._recovery_attempts = recovery_attempts
        self._recovery_delay_seconds = recovery_delay_seconds
        self._sleep_fn = sleep_fn

    def submit_entry(
        self,
        plan: HulkProtectionPlan,
        decision: HulkSmashLiveDecision,
    ) -> HyperliquidOrderAck:
        """Submit and require acknowledgement of one short market entry."""
        identity = self._identity()
        self._telemetry.emit_order_intent(
            **{
                "operation": "entry",
                "side": "sell",
                "requested_notional_usd": plan.requested_notional_usd,
                "mark_price": decision.reference_price,
                "client_order_id": identity,
            },
        )
        ack = self._mutate(
            "entry",
            identity,
            lambda: self._adapter.submit_market_entry(
                side="short",
                requested_notional_usd=plan.requested_notional_usd,
                mark_price=decision.reference_price,
                client_order_id=identity,
            ),
        )
        self._telemetry.emit_ack("entry", ack)
        _require_accepted(ack, "entry", identity)
        return ack

    def place_stop(
        self,
        plan: HulkProtectionPlan,
        venue: SolReconciliationSnapshot,
    ) -> HyperliquidOrderAck:
        """Submit and require acknowledgement of one protective stop."""
        identity = self._identity()
        self._telemetry.emit_order_intent(
            **{
                "operation": "protective_stop",
                "side": "buy",
                "trigger_price": plan.stop_price,
                "reduce_only": True,
                "client_order_id": identity,
            },
        )
        ack = self._mutate(
            "protective_stop",
            identity,
            lambda: self._adapter.place_protective_stop(
                position_size_signed=venue.position.size_signed,
                trigger_price=plan.stop_price,
                client_order_id=identity,
            ),
        )
        self._telemetry.emit_ack("protective_stop", ack, event_type="stop_order")
        _require_accepted(ack, "protective stop", identity)
        return ack

    def place_target(
        self,
        plan: HulkProtectionPlan,
        venue: SolReconciliationSnapshot,
    ) -> HyperliquidOrderAck:
        """Submit and require acknowledgement of one post-only target."""
        identity = self._identity()
        self._telemetry.emit_order_intent(
            **{
                "operation": "target",
                "side": "buy",
                "limit_price": plan.target_price,
                "reduce_only": True,
                "post_only": True,
                "client_order_id": identity,
            },
        )
        ack = self._mutate(
            "target",
            identity,
            lambda: self._adapter.submit_target(
                position_size_signed=venue.position.size_signed,
                limit_price=plan.target_price,
                client_order_id=identity,
            ),
        )
        self._telemetry.emit_ack("target", ack, event_type="target_order")
        _require_accepted(ack, "target", identity)
        return ack

    def close_position(
        self,
        *,
        position_size_signed: float,
        mark_price: float,
        operation: str,
    ) -> HyperliquidOrderAck:
        """Submit a reduce-only close and recover a lost response by client ID."""
        identity = self._identity()
        self._telemetry.emit_order_intent(
            **{
                "operation": operation,
                "position_size_signed": position_size_signed,
                "mark_price": mark_price,
                "client_order_id": identity,
            },
        )
        ack = self._mutate(
            operation,
            identity,
            lambda: self._adapter.close_position(
                position_size_signed=position_size_signed,
                mark_price=mark_price,
                client_order_id=identity,
            ),
        )
        self._telemetry.emit_ack(operation, ack, event_type="close")
        _require_accepted(ack, operation, identity)
        return ack

    def cancel_order(self, oid: int, operation: str) -> HyperliquidOrderAck:
        """Cancel an exact OID and recover a lost response by venue status."""
        self._telemetry.emit_cancel_intent(operation=operation, oid=oid)
        try:
            ack = self._adapter.cancel_order(oid)
        except SolCancelTransportError as exc:
            if exc.oid != oid:
                raise HulkSmashOrderError(
                    f"{operation} transport OID does not match intent"
                ) from exc
            ack = self._recover_cancel(operation, oid)
        self._telemetry.emit_ack(operation, ack)
        if not ack.accepted:
            raise HulkSmashOrderError(
                f"{operation} rejected for oid {oid}: {ack.error or ack.status}"
            )
        return ack

    def _identity(self) -> str:
        return validate_client_order_id(self._client_order_id_fn())

    def _mutate(
        self,
        operation: str,
        identity: str,
        mutation: Callable[[], HyperliquidOrderAck],
    ) -> HyperliquidOrderAck:
        try:
            return mutation()
        except SolOrderTransportError as exc:
            if exc.client_order_id != identity:
                raise HulkSmashOrderError(
                    f"{operation} transport identity does not match intent"
                ) from exc
            return self._recover(operation, identity)

    def _recover(self, operation: str, identity: str) -> HyperliquidOrderAck:
        for attempt in range(self._recovery_attempts):
            try:
                status = self._adapter.order_status_by_client_id(identity)
                return _status_ack(status)
            except HyperliquidOrderUnavailableError as exc:
                if attempt + 1 == self._recovery_attempts:
                    raise HulkSmashOrderAmbiguityError(
                        operation,
                        identity,
                    ) from exc
                self._sleep_fn(self._recovery_delay_seconds)
        raise AssertionError("Hulk recovery loop exhausted")

    def _recover_cancel(self, operation: str, oid: int) -> HyperliquidOrderAck:
        for attempt in range(self._recovery_attempts):
            try:
                return _cancel_status_ack(self._adapter.order_status(oid))
            except HyperliquidOrderUnavailableError as exc:
                if attempt + 1 == self._recovery_attempts:
                    raise HulkSmashOrderAmbiguityError(
                        operation,
                        str(oid),
                    ) from exc
                self._sleep_fn(self._recovery_delay_seconds)
        raise AssertionError("Hulk cancel recovery loop exhausted")


def _require_accepted(
    ack: HyperliquidOrderAck,
    operation: str,
    identity: str,
) -> None:
    if ack.client_order_id != identity:
        raise HulkSmashOrderError(
            f"{operation} acknowledgement identity differs from intent"
        )
    if not ack.accepted or ack.oid is None:
        raise HulkSmashOrderError(f"{operation} rejected: {ack.error or ack.status}")


def _status_ack(status: HyperliquidOrderStatus) -> HyperliquidOrderAck:
    accepted = status.status in {"filled", "open"}
    return HyperliquidOrderAck(
        accepted=accepted,
        oid=status.oid,
        status=status.status,
        filled_size=status.size if status.status == "filled" else None,
        error=None if accepted else status.status,
        client_order_id=status.client_order_id,
        recovered_after_transport_error=True,
        venue_timestamp_ms=status.status_timestamp_ms,
    )


def _cancel_status_ack(status: HyperliquidOrderStatus) -> HyperliquidOrderAck:
    accepted = status.status in {"canceled", "filled"}
    return HyperliquidOrderAck(
        accepted=accepted,
        oid=status.oid,
        status=status.status,
        filled_size=status.size if status.status == "filled" else None,
        error=None if accepted else status.status,
        recovered_after_transport_error=True,
        venue_timestamp_ms=status.status_timestamp_ms,
    )
