"""Shared-cohort adapter for the frozen BTC liquidity-sweep long provider."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.btc_liquidity_sweep_readiness import (
    liquidity_sweep_long_readiness,
)
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.research.liquidity_sweep_long import (
    build_liquidity_sweep_long_decisions,
    completed_hourly_bars,
)

LIQUIDITY_SWEEP_LONG_STRATEGY = "liquidity_sweep_long_1h_stop60_v1"
LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY = "liquidity_sweep_long_1h_stop60_target60_v2"
LIQUIDITY_SWEEP_LONG_STRATEGIES = frozenset(
    {LIQUIDITY_SWEEP_LONG_STRATEGY, LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY}
)
_MINUTE = pd.Timedelta(minutes=1)


class SweepDecisionBuilderProtocol(Protocol):
    """Causal minute-to-hour decision builder used by runtime and tests."""

    def __call__(self, minute_bars: pd.DataFrame) -> pd.DataFrame:
        """Return decisions indexed at each completed hour's final minute."""
        ...


class LiquiditySweepLongCollector:
    """Collect completed one-hour BTC liquidity-sweep long decisions."""

    def __init__(
        self,
        *,
        strategy_id: str = LIQUIDITY_SWEEP_LONG_STRATEGY,
        decision_builder: SweepDecisionBuilderProtocol = (
            build_liquidity_sweep_long_decisions
        ),
    ) -> None:
        if strategy_id not in LIQUIDITY_SWEEP_LONG_STRATEGIES:
            raise ValueError("unsupported liquidity-sweep strategy identity")
        self.strategy_id = strategy_id
        self._decision_builder = decision_builder

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Collect one causal batch from completed one-minute source bars."""
        if symbol != "BTC":
            raise ValueError("liquidity-sweep long provider requires BTC")
        complete = _complete_minutes(bars, observed_at)
        decisions = _validated_decisions(self._decision_builder(complete))
        selected = _selected(decisions, observed_at, after_decision_time_ms)
        hourly = completed_hourly_bars(complete)
        evaluations = tuple(
            _evaluation(timestamp, row, complete, hourly, self.strategy_id)
            for timestamp, row in selected
        )
        intents = tuple(
            _intent(evaluation) for evaluation in evaluations if evaluation.eligible
        )
        return IntentBatch(
            intents=intents,
            latest_decision_time_ms=_latest(evaluations, after_decision_time_ms),
            evaluations=evaluations,
        )


def _complete_minutes(bars: pd.DataFrame, observed_at: pd.Timestamp) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"liquidity-sweep source bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError(
            "liquidity-sweep timestamps must be aware, unique, and ordered"
        )
    observed = _aware_utc(observed_at)
    complete = bars.loc[times + _MINUTE <= observed, sorted(required)].copy()
    if complete.empty:
        raise ValueError("liquidity-sweep source has no completed minute bars")
    complete["timestamp"] = pd.DatetimeIndex(complete["timestamp"]).tz_convert("UTC")
    return complete.set_index("timestamp")


def _validated_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    required = {"entry_direction", "structural_direction"}
    missing = sorted(required.difference(decisions.columns))
    if missing:
        raise ValueError(f"liquidity-sweep decisions missing columns: {missing}")
    if (
        not isinstance(decisions.index, pd.DatetimeIndex)
        or decisions.index.tz is None
        or not decisions.index.is_monotonic_increasing
        or decisions.index.has_duplicates
    ):
        raise ValueError("liquidity-sweep decisions require ordered UTC timestamps")
    return decisions


def _selected(
    decisions: pd.DataFrame,
    observed_at: pd.Timestamp,
    prior: int | None,
) -> tuple[tuple[pd.Timestamp, pd.Series], ...]:
    observed = _aware_utc(observed_at)
    boundary = -1 if prior is None else prior
    output: list[tuple[pd.Timestamp, pd.Series]] = []
    for timestamp, row in decisions.iterrows():
        available = pd.Timestamp(timestamp).tz_convert("UTC") + _MINUTE
        decision_ms = int(available.timestamp() * 1_000)
        if boundary < decision_ms <= int(observed.timestamp() * 1_000):
            output.append((pd.Timestamp(timestamp).tz_convert("UTC"), row))
    return tuple(output)


def _evaluation(
    timestamp: pd.Timestamp,
    row: pd.Series,
    minute_bars: pd.DataFrame,
    hourly_bars: pd.DataFrame,
    strategy_id: str,
) -> ProviderEvaluation:
    decision_at = timestamp + _MINUTE
    eligible = row["entry_direction"] == "long"
    readiness = liquidity_sweep_long_readiness(hourly_bars, timestamp.floor("1h"))
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="BTC",
        decision_time_ms=int(decision_at.timestamp() * 1_000),
        reference_price=float(minute_bars.loc[timestamp, "close"]),
        decision_action="enter_long" if eligible else "hold",
        eligible=eligible,
        reason="entry_signal_present" if eligible else "entry_condition_absent",
        side="long" if eligible else None,
        readiness=readiness,
        trigger="hourly_downside_sweep_reclaim",
    )


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    return StrategyIntent(
        strategy_id=evaluation.strategy_id,
        symbol=evaluation.symbol,
        side="long",
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason="hourly_downside_sweep_reclaim",
    )


def _latest(
    evaluations: tuple[ProviderEvaluation, ...],
    prior: int | None,
) -> int:
    if evaluations:
        return evaluations[-1].decision_time_ms
    return 0 if prior is None else prior


def _aware_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("liquidity-sweep clock must be timezone-aware")
    return timestamp.tz_convert("UTC")
