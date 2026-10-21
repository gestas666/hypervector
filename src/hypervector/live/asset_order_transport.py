"""Typed boundary for ambiguous authenticated Hyperliquid responses."""

from __future__ import annotations

from collections.abc import Callable

from hyperliquid.utils.error import ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.live.asset_order_identity import validate_client_order_id


class AssetOrderTransportError(RuntimeError):
    """A venue mutation may have committed before its response was lost."""

    def __init__(
        self,
        *,
        operation: str,
        client_order_id: str,
        detail: str,
    ) -> None:
        clean_operation = operation.strip()
        if not clean_operation:
            raise ValueError("transport operation must be non-empty")
        self.operation = clean_operation
        self.client_order_id = validate_client_order_id(client_order_id)
        self.detail = detail.strip() or "transport response unavailable"
        self.ambiguous = True
        super().__init__(
            f"{self.operation} response is ambiguous for client order identity"
        )


class AssetCancelTransportError(RuntimeError):
    """An exact cancel may have committed before its response was lost."""

    def __init__(self, *, operation: str, oid: int, detail: str) -> None:
        clean_operation = operation.strip()
        if not clean_operation:
            raise ValueError("cancel operation must be non-empty")
        if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
            raise ValueError("cancel oid must be a positive integer")
        self.operation = clean_operation
        self.oid = oid
        self.detail = detail.strip() or "transport response unavailable"
        self.ambiguous = True
        super().__init__(f"{self.operation} response is ambiguous for oid {oid}")


class HyperliquidBatchOrderTransportError(RuntimeError):
    """A batched order action may have committed before its response was lost."""

    def __init__(
        self,
        *,
        operation: str,
        client_order_ids: tuple[str, ...],
        detail: str,
    ) -> None:
        clean_operation = operation.strip()
        if not clean_operation:
            raise ValueError("batch transport operation must be non-empty")
        identities = tuple(
            validate_client_order_id(value) for value in client_order_ids
        )
        if not identities:
            raise ValueError(
                "batch transport requires at least one client order identity"
            )
        if len(set(identities)) != len(identities):
            raise ValueError("batch client order identities must be unique")
        self.operation = clean_operation
        self.client_order_ids = identities
        self.detail = detail.strip() or "transport response unavailable"
        self.ambiguous = True
        super().__init__(
            f"{self.operation} response is ambiguous for client order identities"
        )


def call_ambiguous_order_mutation(
    *,
    operation: str,
    client_order_id: str,
    mutation: Callable[[], object],
) -> object:
    """Call one mutation and preserve identity on transport/server failure."""
    try:
        return mutation()
    except (RequestException, ServerError) as exc:
        raise AssetOrderTransportError(
            operation=operation,
            client_order_id=client_order_id,
            detail=str(exc),
        ) from exc


def call_ambiguous_batch_order_mutation(
    *,
    operation: str,
    client_order_ids: tuple[str, ...],
    mutation: Callable[[], object],
) -> object:
    """Call one batched mutation and preserve every durable client identity."""
    try:
        return mutation()
    except (RequestException, ServerError) as exc:
        raise HyperliquidBatchOrderTransportError(
            operation=operation,
            client_order_ids=client_order_ids,
            detail=str(exc),
        ) from exc


def call_ambiguous_cancel_mutation(
    *,
    operation: str,
    oid: int,
    mutation: Callable[[], object],
) -> object:
    """Call one exact cancel and preserve its OID on response loss."""
    try:
        return mutation()
    except (RequestException, ServerError) as exc:
        raise AssetCancelTransportError(
            operation=operation,
            oid=oid,
            detail=str(exc),
        ) from exc
