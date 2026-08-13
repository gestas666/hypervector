"""Continuous causal runner for the explicitly armed SOL live engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import math
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.sol_range_onset_state import SolLiveSnapshot
from hypervector.research.range_onset_observation import index_range_onset_bars

_FUNDING_LOOKBACK_MS = 86_400_000
_RETAIN_DAYS = 7


class SolLiveRunnerError(RuntimeError):
    """The live loop cannot start or preserve causal ordering."""


class SolLiveRunnerEngineProtocol(Protocol):
    """Venue lifecycle operations required by the continuous loop."""

    def start(self) -> SolLiveSnapshot:
        """Complete fail-closed venue preflight."""
        ...

    def stop(self, reason: str) -> SolLiveSnapshot:
        """Stop evaluation while preserving native protection."""
        ...

    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> SolReconciliationSnapshot:
        """Reconcile exact venue exposure, fills, fees, and funding."""
        ...


class SolLiveRunnerControllerProtocol(Protocol):
    """Causal completed-bar decision consumer."""

    def process(self, decision: SolLiveDecision) -> SolLiveSnapshot:
        """Persist and route one strictly increasing decision."""
        ...


class SolBarFetcherProtocol(Protocol):
    """Public Hyperliquid OHLCV reader."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int,
    ) -> pd.DataFrame:
        """Return raw OHLCV rows for one bounded lookback."""
        ...


class SolDecisionBuilderProtocol(Protocol):
    """Causal completed-bar decision builder."""

    def __call__(
        self,
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]:
        """Return unseen decisions strictly after the supplied boundary."""
        ...


class SolRangeOnsetLiveRunner:
    """Run read/reconcile/decide cycles without admitting historical signals."""

    def __init__(
        self,
        *,
        engine: SolLiveRunnerEngineProtocol,
        controller: SolLiveRunnerControllerProtocol,
        stop_file: Path,
        fetch_bars: SolBarFetcherProtocol,
        build_decisions: SolDecisionBuilderProtocol,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        poll_seconds: float,
        lookback_days: int,
    ) -> None:
        _validate_settings(poll_seconds, lookback_days)
        self._engine = engine
        self._controller = controller
        self._stop_file = stop_file
        self._fetch_bars = fetch_bars
        self._build_decisions = build_decisions
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._poll_seconds = poll_seconds
        self._lookback_days = lookback_days

    def run(self, *, max_polls: int | None = None) -> int:
        """Run until operator stop or an optional bounded test completion."""
        _validate_max_polls(max_polls)
        if self._stop_file.exists():
            raise SolLiveRunnerError(
                f"live stop file already exists; remove intentionally: {self._stop_file}"
            )
        activation = _utc_timestamp(self._now_fn())
        last_decision_ms = _timestamp_ms(activation)
        bars = self._fetch_bars("SOL", "1m", self._lookback_days)
        decisions = self._decisions(bars, activation, last_decision_ms)
        self._engine.start()
        funding_start_ms = max(0, last_decision_ms - _FUNDING_LOOKBACK_MS)
        try:
            return self._run_cycles(
                bars=bars,
                decisions=decisions,
                observed_at=activation,
                funding_start_ms=funding_start_ms,
                last_decision_ms=last_decision_ms,
                max_polls=max_polls,
            )
        except KeyboardInterrupt:
            self._engine.stop("operator_interrupt")
            raise

    def _run_cycles(
        self,
        *,
        bars: pd.DataFrame,
        decisions: tuple[SolLiveDecision, ...],
        observed_at: pd.Timestamp,
        funding_start_ms: int,
        last_decision_ms: int,
        max_polls: int | None,
    ) -> int:
        polls = 0
        while True:
            if self._stop_file.exists():
                self._engine.stop("operator_stop_file")
                return polls
            observed_ms = _timestamp_ms(observed_at)
            self._engine.reconcile_telemetry(
                funding_start_time_ms=funding_start_ms,
                funding_end_time_ms=observed_ms,
            )
            last_decision_ms = self._process(decisions, last_decision_ms)
            polls += 1
            if max_polls is not None and polls >= max_polls:
                self._engine.stop("bounded_run_complete")
                return polls
            self._sleep_fn(self._poll_seconds)
            observed_at = _utc_timestamp(self._now_fn())
            tail = self._fetch_bars("SOL", "1m", 1)
            bars = _merge_bars(bars, tail, observed_at)
            decisions = self._decisions(bars, observed_at, last_decision_ms)
            funding_start_ms = observed_ms

    def _decisions(
        self,
        bars: pd.DataFrame,
        observed_at: pd.Timestamp,
        after_ms: int,
    ) -> tuple[SolLiveDecision, ...]:
        decisions = self._build_decisions(
            bars,
            observed_at=observed_at,
            after_decision_time_ms=after_ms,
        )
        if any(decision.decision_time_ms <= after_ms for decision in decisions):
            raise SolLiveRunnerError(
                "decision builder returned historical or duplicate data"
            )
        return decisions

    def _process(
        self,
        decisions: tuple[SolLiveDecision, ...],
        last_decision_ms: int,
    ) -> int:
        latest = last_decision_ms
        for decision in decisions:
            if decision.decision_time_ms <= latest:
                raise SolLiveRunnerError("live decisions must be strictly increasing")
            self._controller.process(decision)
            latest = decision.decision_time_ms
        return latest


def _merge_bars(
    prior: pd.DataFrame,
    tail: pd.DataFrame,
    observed_at: pd.Timestamp,
) -> pd.DataFrame:
    combined = pd.concat([prior, tail], ignore_index=True)
    indexed = index_range_onset_bars(combined)
    cutoff = observed_at - pd.Timedelta(days=_RETAIN_DAYS)
    return indexed.loc[indexed.index >= cutoff].reset_index()


def _utc_timestamp(value: datetime) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise SolLiveRunnerError("live runner clock must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.timestamp() * 1_000)


def _validate_settings(poll_seconds: float, lookback_days: int) -> None:
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise SolLiveRunnerError("poll_seconds must be positive and finite")
    if isinstance(lookback_days, bool) or lookback_days < 3:
        raise SolLiveRunnerError("lookback_days must be at least three")


def _validate_max_polls(value: int | None) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
    ):
        raise SolLiveRunnerError("max_polls must be a positive integer")
