"""Continuous completed-30m runner for the explicitly armed Hulk canary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
import math
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision
from hypervector.live.hulk_smash_live_models import (
    HulkSmashLiveSnapshot,
    HulkSmashLiveState,
)

_HISTORY_BARS = 90
_SIGNAL_INTERVAL_MS = 30 * 60 * 1_000


class HulkLiveEngineProtocol(Protocol):
    """Lifecycle operations required by the completed-bar runner."""

    @property
    def snapshot(self) -> HulkSmashLiveSnapshot: ...

    def start(self) -> HulkSmashLiveSnapshot: ...

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None: ...

    def record_strategy_decision(self, decision: HulkSmashLiveDecision) -> None: ...

    def enter(self, decision: HulkSmashLiveDecision) -> HulkSmashLiveSnapshot: ...

    def poll_market(self) -> HulkSmashLiveSnapshot: ...

    def stop(self, reason: str) -> HulkSmashLiveSnapshot: ...


class HulkLiveBarFetcherProtocol(Protocol):
    """Public Hyperliquid candle source required by the runner."""

    def __call__(
        self, symbol: str, timeframe: str, lookback_days: int
    ) -> pd.DataFrame: ...


class HulkLiveDecisionBuilderProtocol(Protocol):
    """Causal completed-bar strategy boundary required by the runner."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[HulkSmashLiveDecision, ...]: ...


class HulkSmashLiveRunnerError(RuntimeError):
    """The live loop cannot preserve causal signal or lifecycle ordering."""


class HulkSmashLiveRunner:
    """Warm history without execution, then route only fresh eligible bars."""

    def __init__(
        self,
        *,
        engine: HulkLiveEngineProtocol,
        stop_file: Path,
        fetch_bars: HulkLiveBarFetcherProtocol,
        build_decisions: HulkLiveDecisionBuilderProtocol,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        lookback_days: int,
        maximum_entry_delay_seconds: int,
        signal_stop_requested: Callable[[], bool],
    ) -> None:
        _validate_settings(
            poll_seconds,
            lookback_days,
            maximum_entry_delay_seconds,
        )
        self._engine = engine
        self._stop_file = stop_file
        self._fetch_bars = fetch_bars
        self._build_decisions = build_decisions
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._lookback_days = lookback_days
        self._maximum_entry_delay_ms = maximum_entry_delay_seconds * 1_000
        self._signal_stop_requested = signal_stop_requested

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until operator stop or bounded test completion."""
        _validate_max_polls(max_polls)
        if self._stop_file.exists():
            raise HulkSmashLiveRunnerError(
                f"live stop file already exists: {self._stop_file}"
            )
        if self._signal_stop_requested():
            raise HulkSmashLiveRunnerError(
                "operator signal stop requested before engine start"
            )
        history = self._history()
        if self._shutdown_requested():
            raise HulkSmashLiveRunnerError("operator stop requested during warmup")
        self._engine.start()
        try:
            self._engine.record_history(history[-_HISTORY_BARS:])
            latest = history[-1].decision_time_ms
            polls = 0
            while not self._shutdown_requested():
                self._engine.poll_market()
                _require_operable(self._engine.snapshot.state)
                latest = self._route(self._fresh(latest), latest)
                polls += 1
                if max_polls is not None and polls >= max_polls:
                    self._engine.stop("bounded_run_complete")
                    return polls
                if self._shutdown_requested():
                    break
                self._sleep_fn(self._poll_seconds)
            reason = (
                "operator_signal"
                if self._signal_stop_requested()
                else "operator_stop_file"
            )
            self._engine.stop(reason)
            return polls
        except KeyboardInterrupt:
            self._stop_if_operable("operator_interrupt")
            raise
        except Exception:
            self._stop_if_operable("runtime_failure")
            raise

    def _history(self) -> tuple[HulkSmashLiveDecision, ...]:
        bars = self._fetch_bars("BTC", "5m", self._lookback_days)
        decisions = self._build_decisions(
            bars,
            observed_at=_utc(self._now_fn()),
            after_decision_time_ms=None,
        )
        if not decisions:
            raise HulkSmashLiveRunnerError("Hulk live warmup is empty")
        _validate_order(decisions, None)
        return decisions

    def _fresh(self, latest: int) -> tuple[HulkSmashLiveDecision, ...]:
        observed = _utc(self._now_fn())
        if _timestamp_ms(observed) < latest + _SIGNAL_INTERVAL_MS:
            return ()
        bars = self._fetch_bars("BTC", "5m", self._lookback_days)
        return self._build_decisions(
            bars,
            observed_at=observed,
            after_decision_time_ms=latest,
        )

    def _stop_if_operable(self, reason: str) -> None:
        state = self._engine.snapshot.state
        if state in {HulkSmashLiveState.FLAT, HulkSmashLiveState.OPEN}:
            self._engine.stop(reason)

    def _shutdown_requested(self) -> bool:
        return self._stop_file.exists() or self._signal_stop_requested()

    def _route(
        self,
        decisions: tuple[HulkSmashLiveDecision, ...],
        latest: int,
    ) -> int:
        _validate_order(decisions, latest)
        boundary = latest
        observed_at_ms = _timestamp_ms(_utc(self._now_fn()))
        for decision in decisions:
            routed = self._entry_freshness(decision, observed_at_ms)
            self._engine.record_strategy_decision(routed)
            if (
                routed.entry_eligible
                and self._engine.snapshot.state is HulkSmashLiveState.FLAT
            ):
                self._engine.enter(routed)
            boundary = decision.decision_time_ms
        return boundary

    def _entry_freshness(
        self,
        decision: HulkSmashLiveDecision,
        observed_at_ms: int,
    ) -> HulkSmashLiveDecision:
        age_ms = observed_at_ms - decision.decision_time_ms
        if age_ms < 0:
            raise HulkSmashLiveRunnerError("Hulk decision cannot be future-dated")
        if not decision.entry_eligible:
            return decision
        if age_ms <= self._maximum_entry_delay_ms:
            return decision
        return replace(decision, entry_eligible=False, reason="stale_decision")


def _validate_order(
    decisions: tuple[HulkSmashLiveDecision, ...],
    after_ms: int | None,
) -> None:
    boundary = after_ms
    for decision in decisions:
        if boundary is not None and decision.decision_time_ms <= boundary:
            raise HulkSmashLiveRunnerError("Hulk decisions must be strictly increasing")
        boundary = decision.decision_time_ms


def _utc(value: datetime) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise HulkSmashLiveRunnerError("live runner clock must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.timestamp() * 1_000)


def _validate_settings(
    poll_seconds: float,
    lookback_days: int,
    maximum_entry_delay_seconds: int,
) -> None:
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise HulkSmashLiveRunnerError("poll_seconds must be positive and finite")
    if isinstance(lookback_days, bool) or lookback_days < 3:
        raise HulkSmashLiveRunnerError("lookback_days must be at least three")
    if (
        isinstance(maximum_entry_delay_seconds, bool)
        or not isinstance(maximum_entry_delay_seconds, int)
        or maximum_entry_delay_seconds <= 0
    ):
        raise HulkSmashLiveRunnerError(
            "maximum_entry_delay_seconds must be a positive integer"
        )


def _validate_max_polls(value: int | None) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise HulkSmashLiveRunnerError("max_polls must be a positive integer")


def _require_operable(state: HulkSmashLiveState) -> None:
    if state not in {HulkSmashLiveState.FLAT, HulkSmashLiveState.OPEN}:
        raise HulkSmashLiveRunnerError(
            f"Hulk live engine left an operable state: {state.value}"
        )
