"""Fail-closed market telemetry for assets without a validated entry route."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY = (
    "research_pending_market_observer_bidirectional_15m_v1"
)
_BAR_DURATION = pd.Timedelta(minutes=15)
_REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


class ResearchPendingMarketObserverCollector:
    """Publish causal market health while making entry emission impossible."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return explicit observe-only evaluations for unseen completed bars."""
        if not symbol.strip():
            raise ValueError("research-pending observer symbol must be non-empty")
        boundary = _boundary(after_decision_time_ms)
        selected = _selected_rows(bars, observed_at, boundary)
        evaluations = tuple(
            _evaluation(symbol, timestamp, row) for timestamp, row in selected
        )
        latest = evaluations[-1].decision_time_ms if evaluations else boundary
        return IntentBatch(
            intents=(), latest_decision_time_ms=latest, evaluations=evaluations
        )


def _selected_rows(
    bars: pd.DataFrame,
    observed_at: pd.Timestamp,
    boundary: int,
) -> tuple[tuple[pd.Timestamp, pd.Series], ...]:
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"research-pending source bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError(
            "research-pending timestamps must be aware, unique, and ordered"
        )
    observed = _aware_utc(observed_at)
    selected: list[tuple[pd.Timestamp, pd.Series]] = []
    for position, timestamp in enumerate(times):
        opened_at = pd.Timestamp(timestamp).tz_convert("UTC")
        completed_at = opened_at + _BAR_DURATION
        decision_ms = int(completed_at.timestamp() * 1_000)
        if boundary < decision_ms <= int(observed.timestamp() * 1_000):
            selected.append((completed_at, bars.iloc[position]))
    return tuple(selected)


def _evaluation(
    symbol: str,
    completed_at: pd.Timestamp,
    row: pd.Series,
) -> ProviderEvaluation:
    close = float(row["close"])
    volume = float(row["volume"])
    if not math.isfinite(close) or close <= 0.0:
        raise ValueError("research-pending close must be positive and finite")
    if not math.isfinite(volume) or volume < 0.0:
        raise ValueError("research-pending volume must be nonnegative and finite")
    return ProviderEvaluation(
        strategy_id=RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
        symbol=symbol,
        decision_time_ms=int(completed_at.timestamp() * 1_000),
        reference_price=close,
        decision_action="observe_only",
        eligible=False,
        reason="strategy_validation_pending",
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=1,
            conditions_required=2,
            blockers=("validated_entry_strategy_missing",),
            indicators=("15M MARKET DATA CURRENT", "ENTRY AUTHORITY NONE"),
            metrics={
                "execution_authority": "none",
                "strategy_validation": "pending",
                "volume": volume,
            },
        ),
        backend_non_action_reason="execution_authority_none",
    )


def _boundary(value: int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("research-pending decision boundary must be nonnegative")
    return value


def _aware_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("research-pending observer clock must be timezone-aware")
    return timestamp.tz_convert("UTC")
