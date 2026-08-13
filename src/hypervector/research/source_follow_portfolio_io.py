"""Bounded archive streaming for source-follow production execution replay."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from heapq import merge
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.hl_events import PublicTradeEvent
from hypervector.data.oxa_api import validate_symbol, validate_window
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_context_io import (
    load_verified_replay_context,
)
from hypervector.research.live_replay_context import database_live_replay_context
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    database_replay_coverage,
    live_database_replay_coverage,
)
from hypervector.research.source_follow_archive_events import (
    ArchiveEvent,
    archive_book_event,
    archive_book_rows,
    archive_trade_event,
    archive_trade_rows,
    live_book_event,
    live_book_rows,
    live_trade_event,
    live_trade_rows,
)
from hypervector.research.source_follow_portfolio_models import (
    SourcePortfolioEvent,
    SourceReplayFunding,
    SourceReplayMark,
)


@dataclass(frozen=True)
class SourcePortfolioArchiveConfig:
    """Paths and bounds for one checksum-verified continuous replay."""

    database_path: Path
    prices_path: Path
    funding_path: Path
    symbol: str
    start: datetime
    end: datetime
    chunk: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        """Validate replay identity and bounded-memory chunk size."""
        validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("source portfolio archive chunk must be positive")


@dataclass(frozen=True)
class LiveSourcePortfolioArchiveConfig:
    """Bounds and gap limits for one recorder-backed portfolio replay."""

    database_path: Path
    symbol: str
    start: datetime
    end: datetime
    chunk: timedelta = timedelta(hours=1)
    maximum_book_gap_seconds: float = 15.0
    maximum_price_gap_seconds: float = 5.0
    maximum_funding_age_seconds: float = 5.0

    def __post_init__(self) -> None:
        """Reject invalid replay bounds and permissive implicit defaults."""
        validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        values = (
            self.chunk.total_seconds(),
            self.maximum_book_gap_seconds,
            self.maximum_price_gap_seconds,
            self.maximum_funding_age_seconds,
        )
        if any(value <= 0.0 for value in values):
            raise ValueError("live portfolio replay gap limits must be positive")


def stream_archive_portfolio_events(
    config: SourcePortfolioArchiveConfig,
) -> Iterator[SourcePortfolioEvent]:
    """Yield full-depth books, trades, marks, and funding causally."""
    with SourcePortfolioArchive(config) as archive:
        yield from archive.events(config.start, config.end)


class SourcePortfolioArchive:
    """Keep verified context and DuckDB state across sparse bounded queries."""

    def __init__(self, config: SourcePortfolioArchiveConfig) -> None:
        self._config = config
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._context: MakerReplayContext | None = None

    def __enter__(self) -> SourcePortfolioArchive:
        """Verify complete evidence and open one read-only database handle."""
        replay = ResearchReplayConfig(
            self._config.database_path,
            self._config.symbol,
            self._config.start,
            self._config.end,
            self._config.chunk,
        )
        coverage = database_replay_coverage(replay, include_trades=True)
        if coverage["empty_book_windows"] != 0:
            raise ValueError("production replay requires gap-free L2 coverage")
        self._context = load_verified_replay_context(
            self._config.prices_path,
            self._config.funding_path,
        )
        self._connection = duckdb.connect(
            str(self._config.database_path), read_only=True
        )
        self._connection.execute("SET TimeZone = 'UTC'")
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Close the read-only database handle."""
        if self._connection is not None:
            self._connection.close()
        self._connection = None

    def events(
        self,
        start: datetime,
        end: datetime,
    ) -> Iterator[SourcePortfolioEvent]:
        """Yield one in-bounds sparse interval in bounded chunks."""
        if start < self._config.start or end > self._config.end or start >= end:
            raise ValueError("sparse archive interval is outside verified bounds")
        if self._connection is None or self._context is None:
            raise RuntimeError("source portfolio archive is not open")
        for chunk_start, chunk_end in _bounded_windows(start, end, self._config.chunk):
            prices, funding = self._context.window(
                pd.Timestamp(chunk_start), pd.Timestamp(chunk_end)
            )
            yield from merge_portfolio_events(
                self._config.symbol,
                archive_book_rows(
                    self._connection,
                    self._config.symbol,
                    chunk_start,
                    chunk_end,
                ),
                archive_trade_rows(
                    self._connection,
                    self._config.symbol,
                    chunk_start,
                    chunk_end,
                ),
                prices,
                funding,
            )


class LiveSourcePortfolioArchive:
    """Read verified live books, trades, marks, and funding without mutation."""

    def __init__(self, config: LiveSourcePortfolioArchiveConfig) -> None:
        self._config = config
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._context: MakerReplayContext | None = None

    def __enter__(self) -> LiveSourcePortfolioArchive:
        """Validate live evidence and open one read-only database handle."""
        replay = ResearchReplayConfig(
            self._config.database_path,
            self._config.symbol,
            self._config.start,
            self._config.end,
            self._config.chunk,
        )
        live_database_replay_coverage(
            replay,
            include_trades=True,
            maximum_book_gap_seconds=self._config.maximum_book_gap_seconds,
        )
        self._context, _ = database_live_replay_context(
            self._config.database_path,
            self._config.symbol,
            self._config.start,
            self._config.end,
            maximum_price_gap_seconds=self._config.maximum_price_gap_seconds,
            maximum_funding_age_seconds=self._config.maximum_funding_age_seconds,
        )
        self._connection = duckdb.connect(
            str(self._config.database_path), read_only=True
        )
        self._connection.execute("SET TimeZone = 'UTC'")
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Close the read-only database handle."""
        if self._connection is not None:
            self._connection.close()
        self._connection = None

    def events(
        self,
        start: datetime,
        end: datetime,
    ) -> Iterator[SourcePortfolioEvent]:
        """Yield one verified recorder interval in bounded chunks."""
        if start < self._config.start or end > self._config.end or start >= end:
            raise ValueError("live archive interval is outside verified bounds")
        if self._connection is None or self._context is None:
            raise RuntimeError("live source portfolio archive is not open")
        for chunk_start, chunk_end in _bounded_windows(start, end, self._config.chunk):
            prices, funding = self._context.window(
                pd.Timestamp(chunk_start), pd.Timestamp(chunk_end)
            )
            books = (
                live_book_event(self._config.symbol, row)
                for row in live_book_rows(
                    self._connection,
                    self._config.symbol,
                    chunk_start,
                    chunk_end,
                )
            )
            trades = (
                live_trade_event(self._config.symbol, row)
                for row in live_trade_rows(
                    self._connection,
                    self._config.symbol,
                    chunk_start,
                    chunk_end,
                )
            )
            yield from merge_normalized_portfolio_events(books, trades, prices, funding)


def merge_portfolio_events(
    symbol: str,
    books: Sequence[tuple[object, ...]],
    trades: Sequence[tuple[object, ...]],
    prices: pd.DataFrame,
    funding: pd.DataFrame,
) -> Iterator[SourcePortfolioEvent]:
    """Merge one bounded evidence chunk with explicit causal priority."""
    book_events = (archive_book_event(symbol, row) for row in books)
    trade_events = (archive_trade_event(symbol, row) for row in trades)
    yield from merge_normalized_portfolio_events(
        book_events, trade_events, prices, funding
    )


def merge_normalized_portfolio_events(
    book_events: Iterable[ArchiveEvent],
    trade_events: Iterable[ArchiveEvent],
    prices: pd.DataFrame,
    funding: pd.DataFrame,
) -> Iterator[SourcePortfolioEvent]:
    """Merge normalized market evidence with causal mark and funding events."""
    mark_events = (
        SourceReplayMark(
            int(row.ts_ms),
            float(row.mark_price),
            float(row.oracle_price),
        )
        for row in prices.itertuples(index=False)
    )
    funding_events = (
        SourceReplayFunding(int(row.event_ts_ms), float(row.funding_rate))
        for row in funding.itertuples(index=False)
    )
    yield from merge(
        mark_events,
        funding_events,
        book_events,
        trade_events,
        key=_event_priority,
    )


def _event_priority(event: SourcePortfolioEvent) -> tuple[int, int, int]:
    if isinstance(event, SourceReplayMark):
        return event.ts_ms, 0, 0
    if isinstance(event, SourceReplayFunding):
        return event.ts_ms, 1, 0
    if isinstance(event, PublicTradeEvent):
        return event.exchange_ts_ms, 3, int(event.trade_id)
    return event.exchange_ts_ms, 2, 0


def _bounded_windows(
    bounded_start: datetime,
    bounded_end: datetime,
    chunk: timedelta,
) -> tuple[tuple[datetime, datetime], ...]:
    result: list[tuple[datetime, datetime]] = []
    start = bounded_start
    while start < bounded_end:
        end = min(start + chunk, bounded_end)
        result.append((start, end))
        start = end
    return tuple(result)
