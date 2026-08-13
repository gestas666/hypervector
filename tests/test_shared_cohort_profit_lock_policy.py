"""Shared causal profit-lock policy contracts for research and live use."""

from __future__ import annotations

import pytest

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    evaluate_profit_lock_path,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.research import cohort_profit_lock_policy as research_policy


def _bar(
    timestamp_ms: int,
    *,
    high: float,
    low: float,
    body: float = 100.0,
) -> CohortMarketBar:
    return CohortMarketBar("BTC", timestamp_ms, body, high, low, body, 1.0)


def test_shared_policy_activates_before_a_later_completed_bar_crosses() -> None:
    """A newly calculated stop cannot execute against the same completed bar."""
    policy = ProfitLockPolicy("provider_lock", 25.0, 15.0, 10.0)
    bars = (
        _bar(0, high=100.30, low=99.90),
        _bar(60_000, high=100.25, low=100.10, body=100.20),
    )

    state = evaluate_profit_lock_path(policy, "long", bars, 100.0)

    assert state.activation_timestamp_ms == 0
    assert state.trigger is not None
    assert state.trigger.trigger_timestamp_ms == 60_000
    assert state.trigger.stop_price == pytest.approx(100.1997)


def test_research_import_is_the_exact_shared_implementation() -> None:
    """Research and future live execution cannot silently diverge in policy math."""
    assert research_policy.ProfitLockPolicy is ProfitLockPolicy
    assert research_policy.evaluate_profit_lock_path is evaluate_profit_lock_path
