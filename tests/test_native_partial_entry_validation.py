"""Fresh protection cannot accept incomplete or changed canceled-entry attribution."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_sol_range_onset_live_engine import _order, _stop_fill, _venue

from hypervector.live.hyperliquid_protocol import HyperliquidOrderAck
from hypervector.live.sol_range_onset_engine_contract import SolLiveEngineError
from hypervector.live.sol_range_onset_verification import verify_canceled_entry_exposure


@pytest.mark.parametrize(
    "change",
    [
        {"venue_timestamp_ms": None},
        {"oid": None},
        {"accepted": False},
        {"filled_size": None},
        {"filled_size": 0.2},
    ],
)
def test_incomplete_canceled_ack_cannot_authorize_protection(change: dict[str, object]) -> None:
    """Proof must include the exact identity, execution boundary and confirmed fill quantity."""
    ack = HyperliquidOrderAck(True, 101, "canceled", filled_size=0.1, venue_timestamp_ms=2000)
    fill = replace(_stop_fill(101, 0.1), side="B", direction="Open Long", timestamp_ms=2000)
    fault = Mock()
    with pytest.raises(SolLiveEngineError, match="conflicts with current exposure"):
        verify_canceled_entry_exposure(replace(ack, **change), _venue(0.1, fills=(fill,)), fault)
    fault.assert_called_once()


@pytest.mark.parametrize("case", ["missing", "changed", "order"])
def test_changed_reconciliation_invalidates_earlier_canceled_fill_proof(case: str) -> None:
    """A later snapshot must still match exact fills and contain no unexplained order."""
    ack = HyperliquidOrderAck(True, 101, "canceled", filled_size=0.1, venue_timestamp_ms=2000)
    fill = replace(_stop_fill(101, 0.1), side="B", direction="Open Long", timestamp_ms=2000)
    stop = _order(202, size=0.1, reduce_only=True, trigger=True)
    venue = _venue(
        0.2 if case == "changed" else 0.1,
        orders=(stop,) if case == "order" else (),
        fills=() if case == "missing" else (fill,),
    )
    with pytest.raises(SolLiveEngineError):
        verify_canceled_entry_exposure(ack, venue, Mock())
