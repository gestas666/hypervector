"""Bounded immutable evidence loading for Apex cohort evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd

from hypervector.research.apex_regime_mm_replay import FundingPoint
from hypervector.research.apex_regime_mm_replay_types import ReplayEvent
from hypervector.research.source_follow_archive_events import (
    archive_book_event,
    archive_book_rows,
    archive_event_sort_key,
    archive_trade_event,
    archive_trade_rows,
)


_MM_SESSION_HOURS = (0, 6, 12, 18)
_MM_SESSION_MINUTE = 5
_MM_SESSION_DURATION_MINUTES = 30


def market_maker_sessions(
    start: datetime,
    end: datetime,
) -> tuple[tuple[datetime, datetime], ...]:
    """Return fixed day-seven intrahour samples for every covered month."""
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    sessions: list[tuple[datetime, datetime]] = []
    while cursor < end:
        for hour in _MM_SESSION_HOURS:
            sample_start = cursor.replace(day=7, hour=hour, minute=_MM_SESSION_MINUTE)
            sample_end = sample_start + timedelta(minutes=_MM_SESSION_DURATION_MINUTES)
            if start <= sample_start and sample_end <= end:
                sessions.append((sample_start, sample_end))
        cursor = _next_month(cursor)
    if not sessions:
        raise ValueError("frozen segment contains no market-maker sample sessions")
    return tuple(sessions)


def archive_events(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[ReplayEvent, ...]:
    """Load and merge one bounded canonical L2 and public-trade session."""
    with duckdb.connect(str(database_path), read_only=True) as connection:
        books = [
            archive_book_event(symbol, row)
            for row in archive_book_rows(connection, symbol, start, end)
        ]
        trades = [
            archive_trade_event(symbol, row)
            for row in archive_trade_rows(connection, symbol, start, end)
        ]
    events = tuple(sorted((*books, *trades), key=archive_event_sort_key))
    if not books or not trades:
        raise ValueError(f"incomplete L2/public-trade evidence for {start.isoformat()}")
    return events


def load_funding(
    path: Path,
    start: datetime,
    end: datetime,
    bar_index: pd.DatetimeIndex,
) -> pd.Series:
    """Validate official hourly coverage and align settlements to exact bars."""
    frame = funding_frame(path, start, end).set_index("timestamp")
    rates = pd.Series(0.0, index=bar_index, dtype=float)
    common = rates.index.intersection(frame.index)
    rates.loc[common] = frame.loc[common, "funding_rate"].to_numpy()
    return rates


def funding_frame(path: Path, start: datetime, end: datetime) -> pd.DataFrame:
    """Load one complete official Hyperliquid hourly funding window."""
    frame = pd.read_parquet(path)
    required = {"timestamp", "funding_rate", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"funding evidence missing columns: {missing}")
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.loc[
        frame["timestamp"].ge(start) & frame["timestamp"].lt(end)
    ].sort_values("timestamp")
    if not frame["source"].eq("hl_funding_history").all():
        raise ValueError("funding evidence must come from hl_funding_history")
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    observed = pd.DatetimeIndex(frame["timestamp"])
    missing_hours = expected.difference(observed)
    if len(missing_hours):
        raise ValueError(
            f"funding evidence is missing {len(missing_hours)} hourly rows"
        )
    if observed.duplicated().any():
        raise ValueError("funding evidence contains duplicate hourly rows")
    return frame.reset_index(drop=True)


def funding_points(
    funding: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> tuple[FundingPoint, ...]:
    """Translate hourly rows within one event session."""
    selected = funding.loc[
        funding["timestamp"].ge(start) & funding["timestamp"].lt(end)
    ]
    return tuple(
        FundingPoint(int(row.timestamp.timestamp() * 1_000), float(row.funding_rate))
        for row in selected.itertuples(index=False)
    )


def indexed(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return a copy indexed by one normalized UTC timestamp column."""
    output = frame.copy()
    output.index = pd.DatetimeIndex(pd.to_datetime(output.pop(column), utc=True))
    return output


def event_sha256(events: Sequence[ReplayEvent]) -> str:
    """Fingerprint normalized chronological event evidence."""
    digest = sha256()
    for event in events:
        digest.update(repr(event).encode())
    return digest.hexdigest()


def _next_month(value: datetime) -> datetime:
    year = value.year + int(value.month == 12)
    month = 1 if value.month == 12 else value.month + 1
    return datetime(year, month, 1, tzinfo=UTC)
