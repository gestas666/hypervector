"""Bounded-memory maker replay access through canonical DuckDB views."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_api import validate_symbol, validate_window
from hypervector.research.maker_replay_stream import MakerReplayEvidenceChunk

DEFAULT_REPLAY_CHUNK = timedelta(days=1)


@dataclass(frozen=True)
class ResearchReplayConfig:
    """Bounds and identity for one canonical database replay stream."""

    database_path: Path
    symbol: str
    start: datetime
    end: datetime
    chunk: timedelta = DEFAULT_REPLAY_CHUNK

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        validate_window(self.start, self.end)
        if self.chunk <= timedelta(0):
            raise ValueError("research replay chunk must be positive")


def database_evidence_chunks(
    config: ResearchReplayConfig,
    *,
    include_trades: bool,
) -> Iterator[MakerReplayEvidenceChunk]:
    """Yield canonical, chronological replay frames without scanning gzip."""
    if not config.database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {config.database_path}")
    with duckdb.connect(str(config.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        _validate_coverage(connection, config)
        empty_books = _empty_book_windows(connection, config)
        for start, end in _evidence_windows(config, empty_books):
            book = _book_frame(connection, config.symbol, start, end)
            trades = (
                _trade_frame(connection, config.symbol, start, end)
                if include_trades
                else None
            )
            yield MakerReplayEvidenceChunk(
                None if book.empty else book,
                None if trades is None or trades.empty else trades,
                pd.Timestamp(start),
                pd.Timestamp(end),
            )


def live_database_evidence_chunks(
    config: ResearchReplayConfig,
    *,
    include_trades: bool,
    maximum_book_gap_seconds: float = 15.0,
) -> Iterator[MakerReplayEvidenceChunk]:
    """Yield validated live-only Hyperliquid evidence for a bounded window."""
    if not config.database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {config.database_path}")
    if maximum_book_gap_seconds <= 0.0:
        raise ValueError("maximum live book gap must be positive")
    with duckdb.connect(str(config.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        _validate_live_coverage(connection, config, maximum_book_gap_seconds)
        for start, end in _chunk_windows(config):
            book = _live_book_frame(connection, config.symbol, start, end)
            trades = (
                _live_trade_frame(connection, config.symbol, start, end)
                if include_trades
                else None
            )
            yield MakerReplayEvidenceChunk(
                None if book.empty else book,
                None if trades is None or trades.empty else trades,
                pd.Timestamp(start),
                pd.Timestamp(end),
            )


def live_database_replay_coverage(
    config: ResearchReplayConfig,
    *,
    include_trades: bool,
    maximum_book_gap_seconds: float = 15.0,
) -> dict[str, object]:
    """Return validated row and gap evidence for one live replay window."""
    if not config.database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {config.database_path}")
    if maximum_book_gap_seconds <= 0.0:
        raise ValueError("maximum live book gap must be positive")
    with duckdb.connect(str(config.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        coverage = _validate_live_coverage(connection, config, maximum_book_gap_seconds)
        trades = (
            _live_window_count(connection, config, "replay_live_public_trades")
            if include_trades
            else 0
        )
    return {**coverage, "public_trades": trades}


def database_replay_coverage(
    config: ResearchReplayConfig,
    *,
    include_trades: bool,
) -> dict[str, object]:
    """Return canonical archive coverage before a production-event replay."""
    if not config.database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {config.database_path}")
    with duckdb.connect(str(config.database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        _validate_coverage(connection, config)
        empty_books = _empty_book_windows(connection, config)
        books = _canonical_window_count(connection, config, "replay_book_snapshots")
        trades = (
            _canonical_window_count(connection, config, "replay_public_trades")
            if include_trades
            else 0
        )
    return {
        "data_source": "duckdb_canonical_replay",
        "database_path": str(config.database_path.resolve()),
        "window_start_utc": config.start.isoformat(),
        "window_end_utc": config.end.isoformat(),
        "book_snapshots": books,
        "public_trades": trades,
        "empty_book_windows": len(empty_books),
        "checksums_verified_on_import": True,
    }


def canonical_trade_bars(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Aggregate deduplicated venue trades into five-minute OHLCV bars."""
    return _canonical_trade_bars(
        database_path,
        symbol,
        start,
        end,
        view="canonical_trade_5m_bars",
    )


def canonical_trade_minute_bars(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Aggregate deduplicated venue trades into one-minute OHLCV bars."""
    return _canonical_trade_bars(
        database_path,
        symbol,
        start,
        end,
        view="canonical_trade_1m_bars",
    )


def _canonical_trade_bars(
    database_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    view: str,
) -> pd.DataFrame:
    validate_symbol(symbol)
    validate_window(start, end)
    if view not in {"canonical_trade_1m_bars", "canonical_trade_5m_bars"}:
        raise ValueError("canonical trade-bar view is not allowed")
    if not database_path.is_file():
        raise FileNotFoundError(f"research database is missing: {database_path}")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        bars = connection.execute(
            f"""
            SELECT
                bar_open_at AS timestamp,
                open,
                high,
                low,
                close,
                volume,
                trade_count
            FROM {view}
            WHERE symbol = ? AND bar_open_at >= ? AND bar_open_at < ?
            ORDER BY bar_open_at
            """,
            [symbol, start, end],
        ).fetchdf()
    if bars.empty:
        raise ValueError("research database produced no trade bars")
    index = pd.DatetimeIndex(pd.to_datetime(bars.pop("timestamp"), utc=True))
    bars.index = index
    if not index.is_monotonic_increasing or not index.is_unique:
        raise RuntimeError("research database returned invalid trade-bar ordering")
    if bars.isna().any(axis=None):
        raise RuntimeError("research database returned incomplete trade bars")
    return bars


def _validate_coverage(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
) -> None:
    rows = connection.execute(
        """
        SELECT start_utc, end_utc
        FROM archive_bundles
        WHERE symbol = ? AND start_utc >= ? AND end_utc <= ?
        ORDER BY start_utc
        """,
        [config.symbol, config.start, config.end],
    ).fetchall()
    expected = pd.Timestamp(config.start)
    if not rows:
        raise ValueError("research database has no bundles for the requested window")
    for row in rows:
        start, end = _window_row(row)
        if start != expected or end <= start:
            raise ValueError("research database archive coverage is not contiguous")
        expected = end
    if expected != pd.Timestamp(config.end):
        raise ValueError("research database does not cover the requested end")


def _validate_live_coverage(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
    maximum_gap_seconds: float,
) -> dict[str, object]:
    start_ms = int(config.start.timestamp() * 1000)
    end_ms = int(config.end.timestamp() * 1000)
    row = connection.execute(
        """
        WITH ordered AS (
            SELECT exchange_ts_ms,
                   lag(exchange_ts_ms) OVER (ORDER BY exchange_ts_ms) AS previous
            FROM replay_live_book_snapshots
            WHERE symbol = ? AND exchange_ts_ms >= ? AND exchange_ts_ms < ?
        )
        SELECT count(*), min(exchange_ts_ms), max(exchange_ts_ms),
               max(exchange_ts_ms - previous)
        FROM ordered
        """,
        [config.symbol, start_ms, end_ms],
    ).fetchone()
    count, first_ms, last_ms, maximum_ms = _live_coverage_values(row)
    permitted_ms = maximum_gap_seconds * 1000.0
    if (
        count == 0
        or first_ms - start_ms > permitted_ms
        or end_ms - last_ms > permitted_ms
    ):
        raise ValueError("live book evidence does not cover the requested bounds")
    if maximum_ms is not None and maximum_ms > permitted_ms:
        raise ValueError("live book evidence exceeds the maximum permitted gap")
    gap_count, recorded_maximum_ms = _validate_recorded_live_gaps(
        connection, config.symbol, start_ms, end_ms, permitted_ms
    )
    return {
        "data_source": "duckdb_live_hyperliquid_events",
        "database_path": str(config.database_path.resolve()),
        "window_start_utc": config.start.isoformat(),
        "window_end_utc": config.end.isoformat(),
        "book_snapshots": count,
        "maximum_book_gap_seconds": 0.0 if maximum_ms is None else maximum_ms / 1000.0,
        "recorded_stream_gaps": gap_count,
        "maximum_recorded_gap_seconds": 0.0
        if recorded_maximum_ms is None
        else recorded_maximum_ms / 1000.0,
        "checksums_verified_on_import": True,
    }


def _live_coverage_values(
    row: tuple[object, ...] | None,
) -> tuple[int, int, int, int | None]:
    if row is None or len(row) != 4 or not isinstance(row[0], int):
        raise RuntimeError("research database returned invalid live coverage")
    if row[0] == 0:
        return 0, 0, 0, None
    if not isinstance(row[1], int) or not isinstance(row[2], int):
        raise RuntimeError("research database returned invalid live bounds")
    maximum = row[3]
    if maximum is not None and not isinstance(maximum, int):
        raise RuntimeError("research database returned invalid live gap")
    return row[0], row[1], row[2], maximum


def _validate_recorded_live_gaps(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start_ms: int,
    end_ms: int,
    permitted_ms: float,
) -> tuple[int, int | None]:
    row = connection.execute(
        """
        SELECT count(*), max(next_exchange_ts_ms - previous_exchange_ts_ms),
               count(*) FILTER (
                   WHERE previous_exchange_ts_ms IS NULL
                      OR next_exchange_ts_ms IS NULL
               )
        FROM live_stream_gaps
        WHERE symbol = ?
          AND coalesce(next_exchange_ts_ms, previous_exchange_ts_ms) >= ?
          AND coalesce(previous_exchange_ts_ms, next_exchange_ts_ms) < ?
        """,
        [symbol, start_ms, end_ms],
    ).fetchone()
    if row is None or len(row) != 3:
        raise RuntimeError("research database returned invalid live gap telemetry")
    count, maximum, unresolved = row
    if not isinstance(count, int) or not isinstance(unresolved, int):
        raise RuntimeError("research database returned invalid live gap counts")
    if maximum is not None and not isinstance(maximum, int):
        raise RuntimeError("research database returned invalid recorded gap")
    if unresolved or (maximum is not None and float(maximum) > permitted_ms):
        raise ValueError("recorded live-stream gap exceeds replay tolerance")
    return count, maximum


def _live_window_count(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
    table: str,
) -> int:
    if table != "replay_live_public_trades":
        raise ValueError(f"unsupported live replay table: {table}")
    row = connection.execute(
        f"""
        SELECT count(*) FROM {table}
        WHERE symbol = ? AND exchange_ts_ms >= epoch_ms(?)
          AND exchange_ts_ms < epoch_ms(?)
        """,
        [config.symbol, config.start, config.end],
    ).fetchone()
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise RuntimeError(f"research database returned invalid count: {table}")
    return row[0]


def _canonical_window_count(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
    table: str,
) -> int:
    if table not in {"replay_book_snapshots", "replay_public_trades"}:
        raise ValueError(f"unsupported canonical replay table: {table}")
    if table == "replay_public_trades":
        row = _canonical_trade_count(connection, config)
    else:
        row = connection.execute(
            """
            SELECT count(*) FROM book_snapshots
            WHERE symbol = ?
              AND ts_exchange_ms >= epoch_ms(?)
              AND ts_exchange_ms < epoch_ms(?)
            """,
            [config.symbol, config.start, config.end],
        ).fetchone()
    if row is None or len(row) != 1 or not isinstance(row[0], int):
        raise RuntimeError(f"research database returned invalid count: {table}")
    return row[0]


def _canonical_trade_count(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
) -> tuple[object, ...] | None:
    return connection.execute(
        """
        SELECT count(*) FROM (
            SELECT trades.trade_id
            FROM public_trades AS trades
            INNER JOIN archive_bundles AS bundles USING (bundle_id)
            WHERE trades.symbol = ?
              AND trades.ts_exchange_ms >= epoch_ms(?)
              AND trades.ts_exchange_ms < epoch_ms(?)
            QUALIFY row_number() OVER (
                PARTITION BY trades.symbol, trades.trade_id
                ORDER BY bundles.start_utc DESC
            ) = 1
        )
        """,
        [config.symbol, config.start, config.end],
    ).fetchone()


def _window_row(row: tuple[object, ...]) -> tuple[pd.Timestamp, pd.Timestamp]:
    if len(row) != 2 or not all(isinstance(value, datetime) for value in row):
        raise RuntimeError("research database returned invalid archive bounds")
    return pd.Timestamp(row[0]), pd.Timestamp(row[1])


def _chunk_windows(
    config: ResearchReplayConfig,
) -> tuple[tuple[datetime, datetime], ...]:
    windows: list[tuple[datetime, datetime]] = []
    start = config.start
    while start < config.end:
        end = min(start + config.chunk, config.end)
        windows.append((start, end))
        start = end
    return tuple(windows)


def _empty_book_windows(
    connection: duckdb.DuckDBPyConnection,
    config: ResearchReplayConfig,
) -> tuple[tuple[datetime, datetime], ...]:
    rows = connection.execute(
        """
        SELECT start_utc, end_utc
        FROM archive_bundles
        WHERE symbol = ? AND start_utc >= ? AND end_utc <= ?
          AND book_rows = 0
        ORDER BY start_utc
        """,
        [config.symbol, config.start, config.end],
    ).fetchall()
    return tuple(_window_row(row) for row in rows)


def _evidence_windows(
    config: ResearchReplayConfig,
    empty_books: tuple[tuple[datetime, datetime], ...],
) -> tuple[tuple[datetime, datetime], ...]:
    """Split bounded-memory chunks at every declared empty-L2 interval."""
    windows: list[tuple[datetime, datetime]] = []
    for chunk_start, chunk_end in _chunk_windows(config):
        cursor = chunk_start
        for gap_start, gap_end in empty_books:
            if gap_end <= chunk_start or gap_start >= chunk_end:
                continue
            bounded_start = max(gap_start, chunk_start)
            bounded_end = min(gap_end, chunk_end)
            if cursor < bounded_start:
                windows.append((cursor, bounded_start))
            windows.append((bounded_start, bounded_end))
            cursor = bounded_end
        if cursor < chunk_end:
            windows.append((cursor, chunk_end))
    return tuple(windows)


def _book_frame(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT
            ts_exchange_ms AS ts_ms,
            best_bid,
            best_ask,
            mid_price AS mid,
            spread_bps,
            imbalance_5 AS obi_5,
            imbalance_10 AS obi_10,
            bid_depth_10,
            ask_depth_10,
            CASE WHEN ask_depth_10 = 0 THEN 1.0
                 ELSE bid_depth_10 / ask_depth_10 END AS book_depth_ratio,
            micro_price,
            10000.0 * (micro_price - mid_price) / mid_price
                AS micro_price_delta_bps
        FROM replay_book_snapshots
        WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
        ORDER BY ts_exchange_ms
        """,
        [symbol, start, end],
    ).fetchdf()


def _live_book_frame(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return connection.execute(
        """
        WITH depth AS (
            SELECT *,
                list_sum(list_transform(list_slice(bids, 1, 5), x -> x.sz)) bd5,
                list_sum(list_transform(list_slice(asks, 1, 5), x -> x.sz)) ad5,
                list_sum(list_transform(list_slice(bids, 1, 10), x -> x.sz)) bd10,
                list_sum(list_transform(list_slice(asks, 1, 10), x -> x.sz)) ad10
            FROM replay_live_book_snapshots
            WHERE symbol = ? AND exchange_ts_ms >= epoch_ms(?)
              AND exchange_ts_ms < epoch_ms(?)
        ), priced AS (
            SELECT *, bids[1].px best_bid, asks[1].px best_ask,
                (bids[1].px + asks[1].px) / 2.0 mid
            FROM depth
        )
        SELECT exchange_ts_ms ts_ms, best_bid, best_ask, mid,
            10000.0 * (best_ask - best_bid) / mid spread_bps,
            CASE WHEN bd5 + ad5 = 0 THEN 0
                 ELSE (bd5 - ad5) / (bd5 + ad5) END obi_5,
            CASE WHEN bd10 + ad10 = 0 THEN 0
                 ELSE (bd10 - ad10) / (bd10 + ad10) END obi_10,
            bd10 bid_depth_10, ad10 ask_depth_10,
            CASE WHEN ad10 = 0 THEN 1.0 ELSE bd10 / ad10 END book_depth_ratio,
            CASE WHEN bids[1].sz + asks[1].sz = 0 THEN mid
                 ELSE ((best_ask * bids[1].sz) + (best_bid * asks[1].sz))
                      / (bids[1].sz + asks[1].sz) END micro_price,
            10000.0 * (micro_price - mid) / mid micro_price_delta_bps
        FROM priced ORDER BY exchange_ts_ms
        """,
        [symbol, start, end],
    ).fetchdf()


def _trade_frame(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT
            ts_exchange_ms AS ts_ms,
            trade_id,
            aggressor_side,
            price,
            size
        FROM public_trades
        WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
        QUALIFY row_number() OVER (
            PARTITION BY symbol, trade_id ORDER BY bundle_id
        ) = 1
        ORDER BY ts_exchange_ms, trade_id
        """,
        [symbol, start, end],
    ).fetchdf()


def _live_trade_frame(
    connection: duckdb.DuckDBPyConnection,
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    return connection.execute(
        """
        SELECT exchange_ts_ms AS ts_ms, trade_id, aggressor_side, price, size
        FROM replay_live_public_trades
        WHERE symbol = ? AND exchange_ts_ms >= epoch_ms(?)
          AND exchange_ts_ms < epoch_ms(?)
        ORDER BY exchange_ts_ms, trade_id
        """,
        [symbol, start, end],
    ).fetchdf()
