"""Sparse DuckDB market-path adapter for BTC absorption lifecycle replay."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.research.btc_subminute_absorption_replay import (
    BtcAbsorptionReplayConfig,
    BtcAbsorptionReplayReport,
    _entry,
    replay_btc_absorption_signals,
)


_BOOK_COLUMNS = (
    "ts_exchange_ms",
    "best_bid",
    "best_ask",
    "mid_price",
    "bids",
    "asks",
)
_TRADE_COLUMNS = ("trade_id", "ts_exchange_ms", "price")
_REQUIRED_RELATIONS: dict[str, frozenset[str]] = {
    "book_snapshots": frozenset(
        {
            "symbol",
            "ts_exchange_ms",
            "best_bid",
            "best_ask",
            "mid_price",
            "bids",
            "asks",
        }
    ),
    "public_trades": frozenset(
        {"symbol", "trade_id", "ts_exchange_ms", "price", "bundle_id"}
    ),
    "archive_bundles": frozenset({"bundle_id", "start_utc"}),
}
_FULL_BOOK_SELECT = """
SELECT ts_exchange_ms, best_bid, best_ask, mid_price, bids, asks
FROM book_snapshots
WHERE symbol = 'BTC' AND ts_exchange_ms >= ? AND ts_exchange_ms <= ?
ORDER BY ts_exchange_ms
LIMIT 1
"""


def replay_btc_absorption_from_database(
    database_path: Path,
    signals: pd.DataFrame,
    funding: pd.Series,
    configs: Sequence[BtcAbsorptionReplayConfig] | None = None,
) -> BtcAbsorptionReplayReport:
    """Replay signals from sparse exact-depth queries without loading full paths."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    scenarios = tuple(configs or (BtcAbsorptionReplayConfig(),))
    if not scenarios or len({row.scenario for row in scenarios}) != len(scenarios):
        raise ValueError(
            "BTC absorption database scenarios must be unique and non-empty"
        )
    reports: list[BtcAbsorptionReplayReport] = []
    with duckdb.connect(str(database_path), read_only=True) as connection:
        _configure(connection)
        _validate_schema(connection)
        for config in scenarios:
            reports.append(_replay_scenario(connection, signals, funding, config))
    return _combined_report(reports)


def _replay_scenario(
    connection: duckdb.DuckDBPyConnection,
    signals: pd.DataFrame,
    funding: pd.Series,
    config: BtcAbsorptionReplayConfig,
) -> BtcAbsorptionReplayReport:
    trades: list[pd.DataFrame] = []
    rejections: dict[str, int] = {}
    occupied_until = -1
    ordered = signals.sort_values(["available_at_utc", "event_id"]).reset_index(
        drop=True
    )
    for _, signal in ordered.iterrows():
        available_ms = int(pd.Timestamp(signal["available_at_utc"]).timestamp() * 1_000)
        if available_ms < occupied_until:
            _increment(rejections, "symbol_position_open")
            continue
        books, public_trades = _sparse_path(connection, signal, funding, config)
        report = replay_btc_absorption_signals(
            signal.to_frame().T,
            books,
            public_trades,
            funding,
            config,
        )
        if report.trades.empty:
            for reason, count in report.rejections.items():
                rejections[reason] = rejections.get(reason, 0) + count
            continue
        trades.append(report.trades)
        occupied_until = int(report.trades.iloc[0]["exit_time_ms"]) + 1
    frame = pd.concat(trades, ignore_index=True) if trades else _empty_trade_output()
    return BtcAbsorptionReplayReport(frame, rejections, len(ordered))


def _sparse_path(
    connection: duckdb.DuckDBPyConnection,
    signal: pd.Series,
    funding: pd.Series,
    config: BtcAbsorptionReplayConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    available_ms = int(pd.Timestamp(signal["available_at_utc"]).timestamp() * 1_000)
    request_ms = available_ms + config.entry_latency_ms
    entry_row = _first_book(
        connection, request_ms, request_ms + config.maximum_entry_book_delay_ms
    )
    if entry_row is None:
        return _book_frame(()), _trade_frame(())
    entry_frame = _book_frame((entry_row,))
    entered, _ = _entry(entry_frame, available_ms, config)
    if entered is None:
        return entry_frame, _trade_frame(())
    deadline = entered.time_ms + config.maximum_hold_seconds * 1_000
    target = entered.price * (1.0 + config.target_bps / 10_000.0)
    stop = entered.price * (1.0 - config.stop_bps / 10_000.0)
    rows = [entry_row]
    rows.extend(
        _candidate_exit_books(
            connection, entered.time_ms, deadline, target, stop, config
        )
    )
    rows.extend(_funding_books(connection, funding, entered.time_ms, deadline, config))
    trade_rows = _stop_trade(connection, entered.time_ms, deadline, stop, config)
    if trade_rows:
        stop_book = _first_book(
            connection,
            int(trade_rows[0][1]),
            int(trade_rows[0][1]) + config.maximum_exit_book_delay_ms,
        )
        if stop_book is not None:
            rows.append(stop_book)
    return _book_frame(_unique_books(rows)), _trade_frame(trade_rows)


def _candidate_exit_books(
    connection: duckdb.DuckDBPyConnection,
    entry_ms: int,
    deadline: int,
    target: float,
    stop: float,
    config: BtcAbsorptionReplayConfig,
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    target_row = _crossing_book(
        connection, entry_ms, deadline, "best_bid", ">=", target
    )
    if target_row is not None:
        rows.append(target_row)
    if config.stop_trigger_proxy == "midpoint":
        stop_row = _crossing_book(
            connection, entry_ms, deadline, "mid_price", "<=", stop
        )
        if stop_row is not None:
            rows.append(stop_row)
    deadline_row = _first_book(
        connection, deadline, deadline + config.maximum_exit_book_delay_ms
    )
    if deadline_row is not None:
        rows.append(deadline_row)
    return rows


def _crossing_book(
    connection: duckdb.DuckDBPyConnection,
    entry_ms: int,
    deadline: int,
    column: str,
    operator: str,
    threshold: float,
) -> tuple[object, ...] | None:
    if (column, operator) not in {("best_bid", ">="), ("mid_price", "<=")}:
        raise ValueError("unsupported BTC absorption crossing query")
    return connection.execute(
        f"""
        SELECT ts_exchange_ms, best_bid, best_ask, mid_price, bids, asks
        FROM book_snapshots
        WHERE symbol='BTC' AND ts_exchange_ms > ? AND ts_exchange_ms <= ?
          AND {column} {operator} ?
        ORDER BY ts_exchange_ms LIMIT 1
        """,
        [entry_ms, deadline, threshold],
    ).fetchone()


def _stop_trade(
    connection: duckdb.DuckDBPyConnection,
    entry_ms: int,
    deadline: int,
    stop: float,
    config: BtcAbsorptionReplayConfig,
) -> tuple[tuple[object, ...], ...]:
    if config.stop_trigger_proxy != "public_trade":
        return ()
    row = connection.execute(
        """
        WITH deduplicated AS (
            SELECT trades.trade_id, trades.ts_exchange_ms, trades.price
            FROM public_trades AS trades
            INNER JOIN archive_bundles AS bundles USING (bundle_id)
            WHERE trades.symbol='BTC' AND trades.ts_exchange_ms > ?
              AND trades.ts_exchange_ms <= ? AND trades.price <= ?
            QUALIFY row_number() OVER (
                PARTITION BY trades.symbol, trades.trade_id
                ORDER BY bundles.start_utc DESC, trades.bundle_id
            ) = 1
        )
        SELECT trade_id, ts_exchange_ms, price
        FROM deduplicated ORDER BY ts_exchange_ms, trade_id LIMIT 1
        """,
        [entry_ms, deadline, stop],
    ).fetchone()
    return () if row is None else (row,)


def _funding_books(
    connection: duckdb.DuckDBPyConnection,
    funding: pd.Series,
    entry_ms: int,
    deadline: int,
    config: BtcAbsorptionReplayConfig,
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for timestamp in funding.index:
        settlement = int(pd.Timestamp(timestamp).timestamp() * 1_000)
        if not entry_ms < settlement <= deadline:
            continue
        row = _first_book(
            connection, settlement, settlement + config.maximum_exit_book_delay_ms
        )
        if row is not None:
            rows.append(row)
    return rows


def _first_book(
    connection: duckdb.DuckDBPyConnection,
    start_ms: int,
    end_ms: int,
) -> tuple[object, ...] | None:
    return connection.execute(_FULL_BOOK_SELECT, [start_ms, end_ms]).fetchone()


def _book_frame(rows: Sequence[tuple[object, ...]]) -> pd.DataFrame:
    return pd.DataFrame(tuple(rows), columns=_BOOK_COLUMNS).sort_values(
        "ts_exchange_ms", ignore_index=True
    )


def _trade_frame(rows: Sequence[tuple[object, ...]]) -> pd.DataFrame:
    return pd.DataFrame(tuple(rows), columns=_TRADE_COLUMNS)


def _unique_books(rows: Sequence[tuple[object, ...]]) -> tuple[tuple[object, ...], ...]:
    keyed = {int(row[0]): row for row in rows}
    return tuple(keyed[key] for key in sorted(keyed))


def _combined_report(
    reports: Sequence[BtcAbsorptionReplayReport],
) -> BtcAbsorptionReplayReport:
    frames = [report.trades for report in reports if not report.trades.empty]
    trades = pd.concat(frames, ignore_index=True) if frames else _empty_trade_output()
    rejections: dict[str, int] = {}
    for report in reports:
        for reason, count in report.rejections.items():
            rejections[reason] = rejections.get(reason, 0) + count
    return BtcAbsorptionReplayReport(
        trades,
        rejections,
        sum(report.attempted_signals for report in reports),
    )


def _empty_trade_output() -> pd.DataFrame:
    empty_signals = pd.DataFrame(
        columns=["event_id", "arm", "symbol", "side", "available_at_utc"]
    )
    empty_books = _book_frame(())
    empty_trades = _trade_frame(())
    empty_funding = pd.Series(
        dtype=float, index=pd.DatetimeIndex([], tz="UTC"), name="funding_rate"
    )
    return replay_btc_absorption_signals(
        empty_signals, empty_books, empty_trades, empty_funding
    ).trades


def _configure(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET enable_progress_bar=false")
    connection.execute("SET threads=2")


def _validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    relations = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(set(_REQUIRED_RELATIONS).difference(relations))
    if missing:
        raise ValueError(f"BTC absorption replay database missing: {missing}")
    for relation, expected in _REQUIRED_RELATIONS.items():
        columns = {
            str(row[0]) for row in connection.execute(f"DESCRIBE {relation}").fetchall()
        }
        absent = sorted(expected.difference(columns))
        if absent:
            raise ValueError(f"{relation} missing replay columns: {absent}")


def _increment(counts: dict[str, int], reason: str) -> None:
    counts[reason] = counts.get(reason, 0) + 1
