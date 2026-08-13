"""Sparse idle-gap orchestration for continuous production execution replay."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioEvent,
    SourcePortfolioReplayConfig,
    SourcePortfolioReport,
    SourceSignal,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplaySession,
)


class SourceEventArchive(Protocol):
    """Bounded event source required by sparse orchestration."""

    def events(
        self,
        start: datetime,
        end: datetime,
    ) -> Iterable[SourcePortfolioEvent]:
        """Return chronological production evidence for one interval."""


@dataclass(frozen=True)
class SparseSourcePortfolioResult:
    """Portfolio result plus evidence-volume reduction telemetry."""

    report: SourcePortfolioReport
    queried_intervals: int
    queried_seconds: float
    window_seconds: float


@dataclass(frozen=True)
class SparseSourcePortfolioAdvance:
    """Evidence-volume telemetry for one segment of a retained session."""

    queried_intervals: int
    queried_seconds: float
    window_seconds: float


def replay_sparse_source_portfolio(
    archive: SourceEventArchive,
    start: datetime,
    end: datetime,
    signals: tuple[SourceSignal, ...],
    config: SourcePortfolioReplayConfig | None = None,
    *,
    active_chunk: timedelta = timedelta(minutes=15),
) -> SparseSourcePortfolioResult:
    """Skip only flat gaps while retaining all actionable event chronology."""
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("sparse replay requires positive aware bounds")
    if active_chunk <= timedelta(0):
        raise ValueError("sparse replay active chunk must be positive")
    resolved = config or SourcePortfolioReplayConfig()
    session = SourcePortfolioReplaySession(signals, resolved)
    advance = advance_sparse_source_portfolio(
        session,
        archive,
        start,
        end,
        signals,
        active_chunk=active_chunk,
    )
    return SparseSourcePortfolioResult(
        session.report(),
        advance.queried_intervals,
        advance.queried_seconds,
        advance.window_seconds,
    )


def advance_sparse_source_portfolio(
    session: SourcePortfolioReplaySession,
    archive: SourceEventArchive,
    start: datetime,
    end: datetime,
    signals: tuple[SourceSignal, ...],
    *,
    active_chunk: timedelta = timedelta(minutes=15),
) -> SparseSourcePortfolioAdvance:
    """Advance one retained portfolio across a gap-free evidence segment."""
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("sparse replay requires positive aware bounds")
    if active_chunk <= timedelta(0):
        raise ValueError("sparse replay active chunk must be positive")
    _validate_signals(signals, start, end)
    resolved = session.config
    cursor = start
    intervals = 0
    seconds = 0.0
    warmup = timedelta(milliseconds=resolved.maximum_oracle_age_ms)
    settle = timedelta(
        seconds=resolved.entry_pulse_seconds + 1.0,
        milliseconds=max(resolved.submit_latency_ms, resolved.cancel_latency_ms),
    )
    for signal in signals:
        signal_at = _signal_time(signal)
        if signal_at < cursor:
            continue
        query_start = max(cursor, signal_at - warmup)
        query_end = min(end, signal_at + settle)
        if query_start < query_end:
            session.apply_all(archive.events(query_start, query_end))
            intervals += 1
            seconds += (query_end - query_start).total_seconds()
            cursor = query_end
        while not session.is_idle and cursor < end:
            query_end = min(end, cursor + active_chunk)
            session.apply_all(archive.events(cursor, query_end))
            intervals += 1
            seconds += (query_end - cursor).total_seconds()
            cursor = query_end
    return SparseSourcePortfolioAdvance(
        intervals,
        seconds,
        (end - start).total_seconds(),
    )


def _validate_signals(
    signals: tuple[SourceSignal, ...],
    start: datetime,
    end: datetime,
) -> None:
    previous: datetime | None = None
    for signal in signals:
        timestamp = _signal_time(signal)
        if not start <= timestamp < end:
            raise ValueError("sparse replay signal falls outside bounds")
        if previous is not None and timestamp <= previous:
            raise ValueError("sparse replay signals must be chronological")
        previous = timestamp


def _signal_time(signal: SourceSignal) -> datetime:
    return datetime.fromisoformat(signal.decision_time_utc.replace("Z", "+00:00"))
