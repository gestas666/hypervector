"""Continuous completed-bar runner for the disarmed Hulk mainnet observer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import math
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.hulk_smash_live_decisions import HulkSmashLiveDecision

_HISTORY_BARS = 90
_SIGNAL_INTERVAL_MS = 30 * 60 * 1_000


class HulkObserverProtocol(Protocol):
    """No-submit observer operations consumed by the runner."""

    def start(self) -> None: ...

    def record_history(self, decisions: tuple[HulkSmashLiveDecision, ...]) -> None: ...

    def process(self, decision: HulkSmashLiveDecision) -> None: ...

    def poll_market(self) -> None: ...


class HulkBarFetcherProtocol(Protocol):
    """Public Hyperliquid candle reader used by the observer."""

    def __call__(
        self, symbol: str, timeframe: str, lookback_days: int
    ) -> pd.DataFrame: ...


class HulkDecisionBuilderProtocol(Protocol):
    """Causal completed-bar builder used by the observer."""

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[HulkSmashLiveDecision, ...]: ...


class HulkSmashObserverRunnerError(RuntimeError):
    """The observer loop cannot preserve causal ordering."""


class HulkSmashObserverRunner:
    """Prime history, then publish only newly available 30-minute decisions."""

    def __init__(
        self,
        *,
        observer: HulkObserverProtocol,
        stop_file: Path,
        fetch_bars: HulkBarFetcherProtocol,
        build_decisions: HulkDecisionBuilderProtocol,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        lookback_days: int,
    ) -> None:
        _validate_settings(poll_seconds, lookback_days)
        self._observer = observer
        self._stop_file = stop_file
        self._fetch_bars = fetch_bars
        self._build_decisions = build_decisions
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._lookback_days = lookback_days

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until stop-file arrival or bounded test completion."""
        _validate_max_polls(max_polls)
        if self._stop_file.exists():
            raise HulkSmashObserverRunnerError(
                f"observer stop file already exists: {self._stop_file}"
            )
        activation = _utc(self._now_fn())
        bars = self._fetch_bars("BTC", "5m", self._lookback_days)
        history = self._build_decisions(
            bars,
            observed_at=activation,
            after_decision_time_ms=None,
        )
        if not history:
            raise HulkSmashObserverRunnerError("Hulk observer warmup is empty")
        self._observer.start()
        self._observer.record_history(history[-_HISTORY_BARS:])
        latest = history[-1].decision_time_ms
        return self._cycles(latest, max_polls)

    def _cycles(self, latest: int, max_polls: int | None) -> int:
        polls = 0
        decisions: tuple[HulkSmashLiveDecision, ...] = ()
        while not self._stop_file.exists():
            self._observer.poll_market()
            latest = self._process(decisions, latest)
            polls += 1
            if max_polls is not None and polls >= max_polls:
                return polls
            self._sleep_fn(self._poll_seconds)
            observed = _utc(self._now_fn())
            decisions = self._fresh(latest, observed)
        return polls

    def _fresh(
        self,
        latest: int,
        observed: pd.Timestamp,
    ) -> tuple[HulkSmashLiveDecision, ...]:
        if _timestamp_ms(observed) < latest + _SIGNAL_INTERVAL_MS:
            return ()
        bars = self._fetch_bars("BTC", "5m", self._lookback_days)
        return self._build_decisions(
            bars,
            observed_at=observed,
            after_decision_time_ms=latest,
        )

    def _process(
        self,
        decisions: tuple[HulkSmashLiveDecision, ...],
        latest: int,
    ) -> int:
        boundary = latest
        for decision in decisions:
            if decision.decision_time_ms <= boundary:
                raise HulkSmashObserverRunnerError(
                    "Hulk decisions must be strictly increasing"
                )
            self._observer.process(decision)
            boundary = decision.decision_time_ms
        return boundary


def _utc(value: datetime) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise HulkSmashObserverRunnerError("observer clock must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.timestamp() * 1_000)


def _validate_settings(poll_seconds: float, lookback_days: int) -> None:
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise HulkSmashObserverRunnerError("poll_seconds must be positive and finite")
    if isinstance(lookback_days, bool) or lookback_days < 3:
        raise HulkSmashObserverRunnerError("lookback_days must be at least three")


def _validate_max_polls(value: int | None) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise HulkSmashObserverRunnerError("max_polls must be a positive integer")
