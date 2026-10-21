"""Shared explicit failure and exact-identity lookup for native startup."""

from typing import NoReturn

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.asset_order_restart import PendingAssetOrderIntent
from hypervector.live.asset_order_submission import (
    AssetOrderRecoveryError,
    AssetOrderSubmission,
    AssetOrderSubmissionError,
)
from hypervector.live.asset_engine_contract import AssetLiveEngineError
from hypervector.live.asset_engine_events import AssetLiveEngineEvents


def _recover_intent_ack(
    events: AssetLiveEngineEvents,
    orders: AssetOrderSubmission,
    pending: PendingAssetOrderIntent,
) -> HyperliquidOrderAck:
    try:
        return orders.recover_existing_intent(
            operation=pending.operation,
            client_order_id=pending.client_order_id,
        )
    except AssetOrderRecoveryError as exc:
        raise AssetLiveEngineError(str(exc)) from exc
    except AssetOrderSubmissionError as exc:
        _fault_and_raise(events, exc)


def _fault_and_raise(events: AssetLiveEngineEvents, error: Exception) -> NoReturn:
    reason = str(error)
    events.fault(reason)
    raise AssetLiveEngineError(reason) from error
