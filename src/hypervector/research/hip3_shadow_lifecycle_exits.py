"""Causal exit selection for report-only HIP-3 lifecycle replays."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from hypervector.cohort_profit_lock_policy import evaluate_profit_lock_path
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.research.hip3_shadow_lifecycle_inputs import (
    HIP3_EXACT_MARK_SOURCES,
    INTERVAL_MS,
    Hip3ShadowMark,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
    LifecycleExitReason,
)
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowBook,
    Hip3ShadowDecision,
)

_MINUTE_MS = 60_000
_CANDLE_SOURCE = "hl"


@dataclass(frozen=True)
class Hip3ShadowExitEvent:
    """First causally available exit event for one shadow lifecycle."""

    reason: LifecycleExitReason
    timestamp_ms: int
    stop_trigger_time_ms: int | None = None


def opposite_entry_exit_time(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    entry_book: Hip3ShadowBook,
    config: Hip3ShadowLifecycleConfig,
) -> int | None:
    """Return the first later opposite onset consumed by the live router."""
    if not config.opposite_entry_exit_enabled:
        return None
    return min(
        (
            candidate.observed_at_ms
            for candidate in decisions
            if candidate.side != decision.side
            and candidate.observed_at_ms > entry_book.recv_ts_ms
        ),
        default=None,
    )


def select_shadow_exit_event(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    marks: Sequence[Hip3ShadowMark],
    signals: pd.DataFrame,
    publication: Mapping[int, int],
    stop: float,
    entry_price: float,
    profit_lock_bars: pd.DataFrame | None,
    config: Hip3ShadowLifecycleConfig,
    opposite_exit_time_ms: int | None = None,
) -> Hip3ShadowExitEvent | None:
    """Return the earliest resolved stop, recipe, lock, or maximum-hold event."""
    deadline = decision.decision_time_ms + config.maximum_hold_minutes * _MINUTE_MS
    candidates = [Hip3ShadowExitEvent("max_hold", deadline)]
    signal_time = _signal_exit_time(decision, signals, publication, entry_book)
    if signal_time is not None and config.signal_exit_enabled:
        candidates.append(Hip3ShadowExitEvent("signal", signal_time))
    if opposite_exit_time_ms is not None and config.opposite_entry_exit_enabled:
        candidates.append(
            Hip3ShadowExitEvent("opposite_strategy_intent", opposite_exit_time_ms)
        )
    stop_mark = _first_stop(decision, entry_book, marks, stop, deadline)
    if stop_mark is not None:
        candidates.append(Hip3ShadowExitEvent("stop", stop_mark, stop_mark))
    base = min(candidates, key=lambda value: value.timestamp_ms)
    lock = _profit_lock_event(
        decision,
        entry_book,
        entry_price,
        profit_lock_bars,
        base.timestamp_ms,
        config,
    )
    if lock is None and config.profit_lock_policy is not None:
        return None
    if lock is not False:
        candidates.append(lock)
    return min(candidates, key=lambda value: value.timestamp_ms)


def _first_stop(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    marks: Sequence[Hip3ShadowMark],
    stop: float,
    deadline: int,
) -> int | None:
    return next(
        (
            mark.timestamp_ms
            for mark in marks
            if mark.source in HIP3_EXACT_MARK_SOURCES
            and entry_book.recv_ts_ms < mark.timestamp_ms <= deadline
            and _stop_crossed(decision.side, mark.price, stop)
        ),
        None,
    )


def _signal_exit_time(
    decision: Hip3ShadowDecision,
    signals: pd.DataFrame,
    publication: Mapping[int, int],
    entry_book: Hip3ShadowBook,
) -> int | None:
    column = "long_exit" if decision.side == "long" else "short_exit"
    candidates: list[int] = []
    for timestamp, value in signals[column].items():
        decision_ms = _timestamp_ms(pd.Timestamp(timestamp)) + INTERVAL_MS
        observed_ms = publication.get(decision_ms)
        if (
            bool(value)
            and observed_ms is not None
            and observed_ms > entry_book.recv_ts_ms
        ):
            candidates.append(observed_ms)
    return min(candidates, default=None)


def _profit_lock_event(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    entry_price: float,
    frame: pd.DataFrame | None,
    horizon_ms: int,
    config: Hip3ShadowLifecycleConfig,
) -> Hip3ShadowExitEvent | None | bool:
    policy = config.profit_lock_policy
    if policy is None:
        return False
    if frame is None:
        raise ValueError("HIP-3 lifecycle profit-lock candles are required")
    bars, complete_to = _profit_lock_bars(
        frame, config.symbol, decision.decision_time_ms, horizon_ms
    )
    state = evaluate_profit_lock_path(policy, decision.side, bars, entry_price)
    if state.trigger is not None:
        return Hip3ShadowExitEvent(
            "profit_lock", state.trigger.trigger_timestamp_ms + _MINUTE_MS
        )
    required_to = horizon_ms // _MINUTE_MS * _MINUTE_MS
    return False if complete_to >= required_to else None


def _profit_lock_bars(
    frame: pd.DataFrame,
    symbol: str,
    entry_ms: int,
    horizon_ms: int,
) -> tuple[tuple[CohortMarketBar, ...], int]:
    required = {"timestamp", "open", "high", "low", "close", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"HIP-3 profit-lock candles missing columns: {missing}")
    if set(frame["source"].astype(str)) != {_CANDLE_SOURCE}:
        raise ValueError(
            "HIP-3 profit-lock candle source must be exact Hyperliquid data"
        )
    rows = frame.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    if rows["timestamp"].duplicated().any():
        raise ValueError("HIP-3 profit-lock candles contain duplicate timestamps")
    rows = rows.sort_values("timestamp")
    first = entry_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    expected = first
    output: list[CohortMarketBar] = []
    for row in rows.itertuples(index=False):
        timestamp = _timestamp_ms(pd.Timestamp(row.timestamp))
        if timestamp < first:
            continue
        if timestamp + _MINUTE_MS > horizon_ms or timestamp != expected:
            break
        output.append(_market_bar(symbol, timestamp, row))
        expected += _MINUTE_MS
    return tuple(output), expected


def _market_bar(symbol: str, timestamp: int, row: object) -> CohortMarketBar:
    return CohortMarketBar(
        symbol,
        timestamp,
        float(getattr(row, "open")),
        float(getattr(row, "high")),
        float(getattr(row, "low")),
        float(getattr(row, "close")),
        0.0,
    )


def _stop_crossed(side: str, mark: float, stop: float) -> bool:
    return mark <= stop if side == "long" else mark >= stop


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.as_unit("ns").value // 1_000_000)
