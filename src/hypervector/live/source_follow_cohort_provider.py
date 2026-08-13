"""Cohort adapter for the measured BTC source-follow signal."""

from __future__ import annotations

from collections import deque
import math

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.regime.pinned_hypertrader import PinnedHypertraderClassifier
from hypervector.regime.source_follow_runtime import (
    SourceFollowDecision,
    SourceFollowRuntime,
)
from hypervector.regime.source_follow_session import SourceFollowSessionSignal
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
    load_source_follow_profile,
)

SOURCE_FOLLOW_COHORT_STRATEGY = "hypervelocity_source_follow_bidirectional_5m_v1"
_REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}
_CACHE_SIZE = 32


def configured_source_follow_collector(
    config: MultiAssetLiveConfig,
) -> SourceFollowCohortCollector | None:
    """Build the measured collector only when its provider is configured."""
    provider = next(
        (
            value
            for value in config.providers
            if value.strategy_id == SOURCE_FOLLOW_COHORT_STRATEGY
        ),
        None,
    )
    if provider is None:
        return None
    if provider.source_profile is None:
        raise ValueError("source-follow provider is missing its validated profile")
    return SourceFollowCohortCollector.from_profile(
        load_source_follow_profile(provider.source_profile)
    )


class SourceFollowCohortCollector:
    """Advance one pinned BTC classifier and expose causal provider batches."""

    def __init__(
        self,
        signal: SourceFollowSessionSignal,
        *,
        minimum_confidence: float,
        minimum_range_bps: float,
        maximum_range_bps: float,
    ) -> None:
        """Store the exact measured signal thresholds used by readiness."""
        _validate_policy(
            minimum_confidence,
            minimum_range_bps,
            maximum_range_bps,
        )
        self._signal = signal
        self._minimum_confidence = minimum_confidence
        self._minimum_range_bps = minimum_range_bps
        self._maximum_range_bps = maximum_range_bps
        self._last_minute: pd.Timestamp | None = None
        self._last_label: pd.Timestamp | None = None
        self._highest_requested_boundary: int | None = None
        self._evaluations: deque[ProviderEvaluation] = deque(maxlen=_CACHE_SIZE)

    @classmethod
    def from_profile(
        cls,
        profile: SourceFollowHypervelocityProfile,
    ) -> SourceFollowCohortCollector:
        """Construct the observe-only adapter from the pinned measured profile."""
        if profile.direction_mode != "source_follow_bidirectional":
            raise ValueError("cohort source-follow profile must be bidirectional")
        runtime = SourceFollowRuntime(
            PinnedHypertraderClassifier(profile.source_backend_root),
            minimum_confidence=profile.minimum_confidence,
            minimum_range_bps=profile.minimum_range_bps,
            maximum_range_bps=profile.maximum_range_bps,
            maximum_hold_seconds=profile.maximum_hold_seconds,
            entry_pulse_seconds=profile.entry_pulse_seconds,
            direction_mode="trend_bidirectional",
        )
        return cls(
            SourceFollowSessionSignal(
                runtime,
                entry_session_utc=profile.entry_session_utc,
            ),
            minimum_confidence=profile.minimum_confidence,
            minimum_range_bps=profile.minimum_range_bps,
            maximum_range_bps=profile.maximum_range_bps,
        )

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return fresh source onsets and report-only setup evaluations."""
        if symbol != "BTC":
            raise ValueError("measured source-follow cohort provider supports BTC only")
        observed = _aware_utc(observed_at)
        boundary = after_decision_time_ms or 0
        seed_query = (
            self._highest_requested_boundary is not None
            and boundary < self._highest_requested_boundary
        )
        self._highest_requested_boundary = max(
            boundary,
            self._highest_requested_boundary or 0,
        )
        self._advance(_completed_minutes(bars, observed))
        observed_ms = int(observed.timestamp() * 1_000)
        evaluations = tuple(
            value
            for value in self._evaluations
            if boundary < value.decision_time_ms <= observed_ms
        )
        intents = (
            ()
            if seed_query
            else tuple(_intent(value) for value in evaluations if value.eligible)
        )
        latest = evaluations[-1].decision_time_ms if evaluations else boundary
        return IntentBatch(intents, latest, evaluations)

    def _advance(self, complete: pd.DataFrame) -> None:
        new_rows = _new_minutes(complete, self._last_minute)
        for row in new_rows.itertuples(index=False):
            timestamp = pd.Timestamp(row.timestamp).tz_convert("UTC")
            decision = self._signal.update_minute(
                timestamp_utc=timestamp.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
            self._last_minute = timestamp
            self._record_new_decision(decision)

    def _record_new_decision(self, decision: SourceFollowDecision | None) -> None:
        if decision is None:
            return
        label = pd.Timestamp(decision.label_time_utc)
        if self._last_label is not None and label <= self._last_label:
            return
        self._evaluations.append(
            _evaluation(
                decision,
                minimum_confidence=self._minimum_confidence,
                minimum_range_bps=self._minimum_range_bps,
                maximum_range_bps=self._maximum_range_bps,
            )
        )
        self._last_label = label


def _completed_minutes(bars: pd.DataFrame, observed: pd.Timestamp) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"source-follow cohort bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("source-follow minute timestamps must be aware and ordered")
    complete = bars.loc[times + pd.Timedelta(minutes=1) <= observed].copy()
    if complete.empty:
        raise ValueError("source-follow cohort has no completed minute bars")
    return complete


def _new_minutes(
    complete: pd.DataFrame,
    last_minute: pd.Timestamp | None,
) -> pd.DataFrame:
    times = pd.DatetimeIndex(complete["timestamp"])
    if last_minute is None:
        gaps = times.to_series().diff().ne(pd.Timedelta(minutes=1))
        start = int(gaps.to_numpy().nonzero()[0][-1]) if gaps.any() else 0
        return complete.iloc[start:].reset_index(drop=True)
    new_rows = complete.loc[times > last_minute].reset_index(drop=True)
    if new_rows.empty:
        return new_rows
    new_times = pd.DatetimeIndex(new_rows["timestamp"])
    expected = pd.date_range(
        last_minute + pd.Timedelta(minutes=1),
        periods=len(new_times),
        freq="1min",
    )
    if not new_times.equals(expected):
        raise ValueError("source-follow live minute feed is not contiguous")
    return new_rows


def _evaluation(
    decision: SourceFollowDecision,
    *,
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
) -> ProviderEvaluation:
    side = _candidate_side(decision)
    return ProviderEvaluation(
        strategy_id=SOURCE_FOLLOW_COHORT_STRATEGY,
        symbol="BTC",
        decision_time_ms=int(decision.available_at_utc.timestamp() * 1_000),
        reference_price=decision.bar_close,
        decision_action=(
            f"enter_{decision.entry_direction}" if decision.entry_eligible else "hold"
        ),
        eligible=decision.entry_eligible,
        reason=decision.exclusion_reason or "source_follow_entry_pulse",
        side=decision.entry_direction if decision.entry_eligible else side,
        readiness=_readiness(
            decision,
            side=side,
            minimum_confidence=minimum_confidence,
            minimum_range_bps=minimum_range_bps,
            maximum_range_bps=maximum_range_bps,
        ),
        trigger="primary_onset" if decision.primary_onset else "none",
        primary_regime=decision.primary,
        state_5m=decision.primary,
        confidence=decision.confidence,
    )


def _readiness(
    decision: SourceFollowDecision,
    *,
    side: str | None,
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
) -> SignalReadiness:
    directional_onset = decision.primary_onset and side is not None
    confidence_ready = decision.confidence >= minimum_confidence
    range_ready = minimum_range_bps <= decision.signal_range_bps <= maximum_range_bps
    blockers = _blockers(
        decision,
        side,
        confidence_ready,
        minimum_range_bps,
        maximum_range_bps,
    )
    return SignalReadiness(
        side=side,
        conditions_met=sum((directional_onset, confidence_ready, range_ready)),
        conditions_required=3,
        blockers=blockers,
        indicators=(
            f"5M {decision.primary}",
            f"ONSET {'YES' if decision.primary_onset else 'NO'}",
            f"CONF {decision.confidence * 100.0:.0f}/{minimum_confidence * 100.0:.0f}",
            f"RANGE {decision.signal_range_bps:.1f} [{minimum_range_bps:.1f},{maximum_range_bps:.1f}]",
        ),
        metrics={
            "primary_onset": decision.primary_onset,
            "source_event": decision.source_event,
            "confidence": decision.confidence,
            "minimum_confidence": minimum_confidence,
            "signal_range_bps": decision.signal_range_bps,
            "minimum_range_bps": minimum_range_bps,
            "maximum_range_bps": maximum_range_bps,
        },
    )


def _blockers(
    decision: SourceFollowDecision,
    side: str | None,
    confidence_ready: bool,
    minimum_range_bps: float,
    maximum_range_bps: float,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not decision.primary_onset or side is None:
        blockers.append(
            "awaiting_primary_onset"
            if side is not None
            else "source_primary_not_directional"
        )
    if not confidence_ready:
        blockers.append("source_confidence_below_minimum")
    if decision.signal_range_bps < minimum_range_bps:
        blockers.append("source_range_below_minimum")
    elif decision.signal_range_bps > maximum_range_bps:
        blockers.append("source_range_above_maximum")
    return tuple(blockers)


def _candidate_side(decision: SourceFollowDecision) -> str | None:
    if decision.primary == "TREND_DOWN":
        return "short"
    if decision.primary == "TREND_UP":
        return "long"
    if (
        decision.primary == "BREAKOUT"
        and (decision.secondary or "").upper() == "BK_UPWARD"
    ):
        return "long"
    return None


def _intent(evaluation: ProviderEvaluation) -> StrategyIntent:
    if evaluation.side not in {"long", "short"}:
        raise ValueError("eligible source-follow evaluation is missing a side")
    return StrategyIntent(
        strategy_id=SOURCE_FOLLOW_COHORT_STRATEGY,
        symbol=evaluation.symbol,
        side=evaluation.side,
        decision_time_ms=evaluation.decision_time_ms,
        reference_price=evaluation.reference_price,
        reason=f"source_follow_entry_pulse:{evaluation.primary_regime}",
    )


def _aware_utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("source-follow observation clock must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _validate_policy(
    minimum_confidence: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
) -> None:
    if not math.isfinite(minimum_confidence) or not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError("source-follow minimum confidence must be within [0, 1]")
    ranges = (minimum_range_bps, maximum_range_bps)
    if not all(math.isfinite(value) and value >= 0.0 for value in ranges):
        raise ValueError("source-follow range bounds must be finite and nonnegative")
    if minimum_range_bps > maximum_range_bps:
        raise ValueError("source-follow minimum range exceeds maximum")
