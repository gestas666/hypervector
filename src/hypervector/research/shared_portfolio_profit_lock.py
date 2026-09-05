"""Causal completed-bar profit locks for shared portfolio research."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    evaluate_profit_lock_path,
)
from hypervector.research.shared_portfolio_models import Direction


@dataclass(frozen=True)
class _ResearchProfitLockBar:
    """One completed research bar accepted by the shared lock evaluator."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def completed_bar_profit_lock_triggered(
    bars: pd.DataFrame,
    *,
    entry_position: int,
    current_position: int,
    direction: Direction,
    entry_price: float,
    policy: ProfitLockPolicy | None,
) -> bool:
    """Return whether the policy first triggers on the current completed bar."""
    if policy is None:
        return False
    path = tuple(
        _bar(bars, position) for position in range(entry_position, current_position + 1)
    )
    state = evaluate_profit_lock_path(policy, direction, path, entry_price)
    return bool(
        state.trigger is not None
        and state.trigger.trigger_timestamp_ms == path[-1].timestamp_ms
    )


def _bar(bars: pd.DataFrame, position: int) -> _ResearchProfitLockBar:
    timestamp = pd.Timestamp(bars.index[position])
    return _ResearchProfitLockBar(
        timestamp_ms=int(timestamp.timestamp() * 1_000),
        open=float(bars["open"].iloc[position]),
        high=float(bars["high"].iloc[position]),
        low=float(bars["low"].iloc[position]),
        close=float(bars["close"].iloc[position]),
    )
