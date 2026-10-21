"""Partial state updates require exact fills and sufficient sole owned protection."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_asset_live_engine import _order, _stop_fill, _venue

from hypervector.live.asset_partial_close import acknowledge_protected_partial_close
from hypervector.live.asset_engine_events import AssetLiveEngineEvents
from hypervector.live.asset_state import AssetLiveStateError, AssetLiveStateMachine


def pending_close() -> AssetLiveStateMachine:
    """Build a real state machine with owned protection and one acknowledged close."""
    machine = AssetLiveStateMachine()
    machine.begin_preflight()
    machine.restore_protected_position(
        entry_oid=101,
        stop_oid=202,
        position_size_signed=0.3,
        opened_at_ms=1000,
    )
    machine.begin_exit()
    machine.acknowledge_close(303)
    return machine


@pytest.mark.parametrize("remaining", [0.0, -0.1, 0.3, 0.4, float("nan"), True])
def test_partial_state_rejects_non_reductions_atomically(remaining: float) -> None:
    """Partial acknowledgement cannot enlarge, flip, erase or corrupt a position."""
    machine = pending_close()
    before = machine.snapshot
    with pytest.raises(AssetLiveStateError):
        machine.acknowledge_partial_close(position_size_signed=remaining)
    assert machine.snapshot == before


@pytest.mark.parametrize("case", ["missing", "extra", "foreign", "small", "side", "fills"])
def test_partial_recovery_cannot_accept_unknown_or_insufficient_protection(case: str) -> None:
    """The helper changes no state or telemetry when remaining ownership is unverified."""
    machine = pending_close()
    before = machine.snapshot
    events = Mock(spec=AssetLiveEngineEvents)
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    fill = replace(_stop_fill(oid=303, size=0.1), timestamp_ms=2000)
    orders = (stop,)
    if case == "missing":
        orders = ()
    elif case == "extra":
        orders = (stop, replace(stop, oid=999))
    elif case in {"foreign", "small", "side"}:
        change = {"foreign": {"oid": 999}, "small": {"size": 0.1}, "side": {"side": "B"}}
        orders = (replace(stop, **change[case]),)
    fills = () if case == "fills" else (fill,)
    assert not acknowledge_protected_partial_close(
        venue=_venue(0.2, orders=orders, fills=fills),
        close_oid=303,
        machine=machine,
        events=events,
    )
    assert machine.snapshot == before and not events.mock_calls
