"""Continuous completed-5m runner for the BTC source-follow live canary."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.source_follow_live_engine import SourceFollowLiveSnapshot
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowDecision,
)

_BAR_DURATION = timedelta(minutes=5)
_CHART_HISTORY_BARS = 90


class SourceFollowLiveRunnerError(RuntimeError):
    """The source feed cannot preserve causal completed-bar ordering."""


class SourceFollowBarFetcherProtocol(Protocol):
    """Public OHLCV source required by the live runner."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int,
    ) -> pd.DataFrame: ...


class SourceFollowEngineProtocol(Protocol):
    """Lifecycle operations consumed by the continuous runner."""

    def start(self) -> SourceFollowLiveSnapshot: ...

    def process(
        self,
        decision: SourceFollowDecision | None,
    ) -> SourceFollowLiveSnapshot: ...

    def record_history(self, decisions: tuple[SourceFollowDecision, ...]) -> None: ...


class SourceFollowRuntimeProtocol(Protocol):
    """Pinned completed-bar classifier boundary."""

    def update(self, bar: FiveMinuteBar) -> SourceFollowDecision: ...


class SourceFollowLiveRunner:
    """Warm the pinned classifier, then process only newly completed 5m bars."""

    def __init__(
        self,
        *,
        engine: SourceFollowEngineProtocol,
        runtime: SourceFollowRuntimeProtocol,
        fetch_bars: SourceFollowBarFetcherProtocol,
        stop_file: Path,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        lookback_days: int,
        entry_pulse_seconds: float,
    ) -> None:
        if poll_seconds <= 0.0:
            raise SourceFollowLiveRunnerError("poll_seconds must be positive")
        if lookback_days < 2:
            raise SourceFollowLiveRunnerError("lookback_days must be at least two")
        self._engine = engine
        self._runtime = runtime
        self._fetch_bars = fetch_bars
        self._stop_file = stop_file
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._lookback_days = lookback_days
        self._entry_pulse_seconds = entry_pulse_seconds
        self._last_bar_time: datetime | None = None

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until operator stop or an optional bounded test completion."""
        if max_polls is not None and max_polls <= 0:
            raise SourceFollowLiveRunnerError("max_polls must be positive")
        if self._stop_file.exists():
            raise SourceFollowLiveRunnerError(
                f"live stop file already exists; remove intentionally: {self._stop_file}"
            )
        activation = _utc(self._now_fn())
        history = self._prime(activation)
        self._engine.start()
        self._engine.record_history(history)
        polls = 0
        while not self._stop_file.exists():
            observed = _utc(self._now_fn())
            self._engine.process(None)
            for decision in self._new_decisions(observed):
                if self._stop_file.exists():
                    return polls
                decision_time = _utc(self._now_fn())
                self._engine.process(self._freshness_adjusted(decision, decision_time))
            polls += 1
            if max_polls is not None and polls >= max_polls:
                return polls
            self._sleep_fn(self._poll_seconds)
        return polls

    def _prime(self, observed_at: datetime) -> tuple[SourceFollowDecision, ...]:
        frame = self._fetch_bars("BTC", "5m", self._lookback_days)
        bars = _completed_bars(frame, observed_at)
        if not bars:
            raise SourceFollowLiveRunnerError(
                "BTC 5m warmup returned no completed bars"
            )
        history: deque[SourceFollowDecision] = deque(maxlen=_CHART_HISTORY_BARS)
        for bar in bars:
            history.append(self._runtime.update(bar))
            self._last_bar_time = bar.timestamp_utc
        return tuple(history)

    def _new_decisions(self, observed_at: datetime) -> tuple[SourceFollowDecision, ...]:
        frame = self._fetch_bars("BTC", "5m", 2)
        decisions: list[SourceFollowDecision] = []
        for bar in _completed_bars(frame, observed_at):
            if (
                self._last_bar_time is not None
                and bar.timestamp_utc <= self._last_bar_time
            ):
                continue
            decisions.append(self._runtime.update(bar))
            self._last_bar_time = bar.timestamp_utc
        return tuple(decisions)

    def _freshness_adjusted(
        self,
        decision: SourceFollowDecision,
        observed_at: datetime,
    ) -> SourceFollowDecision:
        expires = decision.available_at_utc + timedelta(
            seconds=self._entry_pulse_seconds
        )
        if not decision.entry_eligible or observed_at < expires:
            return decision
        return replace(
            decision,
            entry_eligible=False,
            entry_direction=None,
            exclusion_reason="entry_pulse_expired",
        )


def _completed_bars(
    frame: pd.DataFrame, observed_at: datetime
) -> tuple[FiveMinuteBar, ...]:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SourceFollowLiveRunnerError(f"BTC 5m bars missing columns: {missing}")
    completed: list[FiveMinuteBar] = []
    for row in frame.sort_values("timestamp").itertuples(index=False):
        timestamp = pd.Timestamp(row.timestamp)
        if timestamp.tzinfo is None:
            raise SourceFollowLiveRunnerError(
                "BTC 5m timestamps must be timezone-aware"
            )
        stamp = timestamp.tz_convert("UTC").to_pydatetime().astimezone(UTC)
        if stamp + _BAR_DURATION > observed_at:
            continue
        completed.append(
            FiveMinuteBar(
                timestamp_utc=stamp,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
        )
    return tuple(completed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceFollowLiveRunnerError("runner clock must be timezone-aware")
    return value.astimezone(UTC)
