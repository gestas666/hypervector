"""Owned execution evidence must explain quantity without trusting terminal labels."""

from dataclasses import replace

import pytest
from test_sol_range_onset_live_engine import _order, _stop_fill, _venue

from hypervector.live.hyperliquid_protocol import HyperliquidOrderStatus
from hypervector.live.sol_execution_evidence import (
    canceled_close_fill_size,
    canceled_close_has_no_observed_fill,
    canceled_entry_fill_size,
    partial_close_size,
)
from hypervector.live.sol_protective_order import protective_stop_covers
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState


@pytest.mark.parametrize("sign", [1, -1])
def test_owned_partial_close_explains_the_exact_remainder(sign: int) -> None:
    """Both directions retain only the original position minus exact owned close fills."""
    state = SolLiveSnapshot(
        SolLiveState.EXIT_PENDING,
        entry_oid=101,
        stop_oid=202,
        position_size_signed=sign * 0.3,
        opened_at_ms=1000,
    )
    fill = replace(
        _stop_fill(oid=303, size=0.1),
        side="A" if sign > 0 else "B",
        direction="Close Long" if sign > 0 else "Close Short",
        timestamp_ms=2000,
    )
    venue = _venue(sign * 0.2, fills=(fill,))
    assert partial_close_size(state, venue, 303) == sign * 0.2
    assert partial_close_size(state, replace(venue, fills=(fill, fill)), 303) is None


@pytest.mark.parametrize(
    "change", ["missing", "foreign", "side", "direction", "old", "negative", "oversize", "trade_id"]
)
def test_partial_close_rejects_incomplete_or_contradictory_fills(change: str) -> None:
    """A changed position alone cannot establish an owned partial close."""
    state = SolLiveSnapshot(
        SolLiveState.EXIT_PENDING,
        entry_oid=101,
        stop_oid=202,
        position_size_signed=0.3,
        opened_at_ms=1000,
    )
    fill = replace(_stop_fill(oid=303, size=0.1), timestamp_ms=2000)
    changes = {
        "foreign": {"oid": 999},
        "side": {"side": "B"},
        "direction": {"direction": "Open Short"},
        "old": {"timestamp_ms": 999},
        "negative": {"size": -0.1},
        "oversize": {"size": 0.3},
        "trade_id": {"trade_id": 0},
    }
    fills = () if change == "missing" else (replace(fill, **changes[change]),)
    assert partial_close_size(state, _venue(0.2, fills=fills), 303) is None


@pytest.mark.parametrize("sign", [1, -1])
def test_canceled_entry_uses_exact_fills_and_current_exposure(sign: int) -> None:
    """A canceled remainder can coexist with an authenticated owned entry fill."""
    status = HyperliquidOrderStatus(101, "SOL", "canceled", 0.2, 2000, original_size=0.3)
    fill = replace(
        _stop_fill(oid=101, size=0.1),
        price=73.1,
        side="B" if sign > 0 else "A",
        direction="Open Long" if sign > 0 else "Open Short",
        timestamp_ms=2000,
        closed_pnl_usd=0,
    )
    venue = _venue(sign * 0.1, fills=(fill,))
    assert canceled_entry_fill_size(status, venue) == 0.1
    assert canceled_entry_fill_size(status, replace(venue, fills=(fill, fill))) is None
    assert canceled_entry_fill_size(replace(status, status_timestamp_ms=1999), venue) is None
    assert canceled_entry_fill_size(status, _venue(sign * 0.2, fills=(fill,))) is None


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("size", [0.2, 0.3])
def test_owned_reduce_only_stop_can_cover_a_reduced_position(sign: int, size: float) -> None:
    """A fixed-size stop remains protective while its reduce-only coverage is sufficient."""
    stop = _order(202, size=size, reduce_only=True, trigger=True, side="A" if sign > 0 else "B")
    assert protective_stop_covers(stop, sign * 0.2)


@pytest.mark.parametrize(
    "change",
    [
        {"size": 0.1},
        {"reduce_only": False},
        {"is_trigger": False},
        {"side": "B"},
        {"size": float("nan")},
        {"size": float("inf")},
    ],
)
def test_stop_coverage_rejects_undercoverage_and_invalid_order(change: dict[str, object]) -> None:
    """Coverage requires the correct direction, trigger and reduce-only semantics."""
    stop = _order(202, size=0.3, reduce_only=True, trigger=True)
    assert not protective_stop_covers(replace(stop, **change), 0.2)


def test_canceled_fill_evidence_rejects_missing_request_and_contradictory_exposure() -> None:
    """Terminal labels, missing original close size and over-request fills are insufficient."""
    status = HyperliquidOrderStatus(101, "SOL", "canceled", 0.0, 2000, original_size=0.3)
    fill = replace(
        _stop_fill(oid=101, size=0.1), side="B", direction="Open Long", timestamp_ms=2000
    )
    venue = _venue(0.1, fills=(fill,))
    assert canceled_entry_fill_size(replace(status, status="rejected"), venue) is None
    assert canceled_entry_fill_size(status, _venue(0)) is None
    assert canceled_entry_fill_size(status, _venue(float("nan"))) is None
    stop = _order(202, size=0.1, reduce_only=True, trigger=True)
    assert canceled_entry_fill_size(status, replace(venue, open_orders=(stop,))) is None
    assert canceled_entry_fill_size(replace(status, original_size=0.05), venue) is None
    assert canceled_entry_fill_size(replace(status, original_size=None), venue) == 0.1
    assert canceled_close_fill_size(replace(status, original_size=None), venue) is None
    assert canceled_close_has_no_observed_fill(status, _venue(0.3))
    assert not canceled_close_has_no_observed_fill(status, _venue(0.3, fills=(fill,)))
    assert not canceled_close_has_no_observed_fill(replace(status, original_size=None), venue)


def test_partial_close_needs_prior_clock_and_matching_direction() -> None:
    """No inferred lifecycle origin or position flip can satisfy close attribution."""
    state = SolLiveSnapshot(SolLiveState.EXIT_PENDING, position_size_signed=0.3)
    assert partial_close_size(state, _venue(0.2), 303) is None
    state = replace(state, opened_at_ms=1000)
    for remaining in (0.0, -0.2, 0.3, float("nan")):
        assert partial_close_size(state, _venue(remaining), 303) is None
