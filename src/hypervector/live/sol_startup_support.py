"""Shared explicit failure and exact-identity lookup for native startup."""

from typing import NoReturn

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_order_restart import PendingSolOrderIntent
from hypervector.live.sol_order_submission import (
    SolOrderRecoveryError,
    SolOrderSubmission,
    SolOrderSubmissionError,
)
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_engine_events import SolLiveEngineEvents


def _recover_intent_ack(
    events: SolLiveEngineEvents,
    orders: SolOrderSubmission,
    pending: PendingSolOrderIntent,
) -> HyperliquidOrderAck:
    try:
        return orders.recover_existing_intent(
            operation=pending.operation,
            client_order_id=pending.client_order_id,
        )
    except SolOrderRecoveryError as exc:
        raise SolLiveEngineError(str(exc)) from exc
    except SolOrderSubmissionError as exc:
        _fault_and_raise(events, exc)


def _fault_and_raise(events: SolLiveEngineEvents, error: Exception) -> NoReturn:
    reason = str(error)
    events.fault(reason)
    raise SolLiveEngineError(reason) from error
