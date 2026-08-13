"""Independent market-tape and L2 evidence for source-follow live audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
import math
from pathlib import Path

import duckdb

_MISMATCH_SAMPLE_LIMIT = 20
_FLOAT_TOLERANCE = 1e-9
_L2_GAP_THRESHOLD_SECONDS = 6.0
_FIVE_MINUTES_MS = 300_000


@dataclass(frozen=True)
class LedgerCandle:
    """Validated backend candle used only as live-audit evidence."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    event_type: str


@dataclass(frozen=True)
class _TradeBar:
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_candidates: tuple[float, ...]
    close_candidates: tuple[float, ...]


def trade_bar_parity(
    database_path: Path,
    candles: Sequence[LedgerCandle],
    symbol: str,
) -> dict[str, object]:
    """Compare backend OHLCV with independently recorded public trades."""
    if not database_path.is_file():
        raise FileNotFoundError(f"research database does not exist: {database_path}")
    trade_bars = _load_trade_bars(database_path, candles, symbol)
    covered = [candle for candle in candles if candle.timestamp in trade_bars]
    uncovered = [candle for candle in candles if candle.timestamp not in trade_bars]
    comparisons = [
        _bar_comparison(candle, trade_bars[candle.timestamp]) for candle in covered
    ]
    mismatches = [item for item in comparisons if not item["exact_ohlcv"]]
    return {
        "database_path": str(database_path.resolve()),
        "ledger_bars": len(candles),
        "trade_bars_covered": len(covered),
        "trade_bars_uncovered": len(uncovered),
        "exact_ohlcv_rows": len(comparisons) - len(mismatches),
        "mismatched_rows": len(mismatches),
        "venue_equivalent_ohlcv_rows": sum(
            item["venue_equivalent_ohlcv"] is True for item in comparisons
        ),
        "boundary_ambiguous_rows": sum(
            item["boundary_ambiguous"] is True for item in comparisons
        ),
        "non_equivalent_rows": sum(
            item["venue_equivalent_ohlcv"] is False for item in comparisons
        ),
        "maximum_absolute_difference": _maximum_differences(comparisons),
        "mismatches": mismatches[:_MISMATCH_SAMPLE_LIMIT],
        "uncovered": [
            candle.timestamp.isoformat()
            for candle in uncovered[:_MISMATCH_SAMPLE_LIMIT]
        ],
        "by_event_type": {
            event_type: _parity_counts(
                [candle for candle in candles if candle.event_type == event_type],
                trade_bars,
            )
            for event_type in sorted({candle.event_type for candle in candles})
        },
    }


def _parity_counts(
    candles: Sequence[LedgerCandle],
    trade_bars: Mapping[datetime, _TradeBar],
) -> dict[str, int]:
    covered = [candle for candle in candles if candle.timestamp in trade_bars]
    comparisons = [
        _bar_comparison(candle, trade_bars[candle.timestamp]) for candle in covered
    ]
    mismatched = sum(item["exact_ohlcv"] is False for item in comparisons)
    equivalent = sum(item["venue_equivalent_ohlcv"] is True for item in comparisons)
    ambiguous = sum(item["boundary_ambiguous"] is True for item in comparisons)
    return {
        "ledger_bars": len(candles),
        "trade_bars_covered": len(covered),
        "trade_bars_uncovered": len(candles) - len(covered),
        "exact_ohlcv_rows": len(covered) - mismatched,
        "mismatched_rows": mismatched,
        "venue_equivalent_ohlcv_rows": equivalent,
        "boundary_ambiguous_rows": ambiguous,
        "non_equivalent_rows": len(covered) - equivalent,
    }


def _load_trade_bars(
    database_path: Path,
    candles: Sequence[LedgerCandle],
    symbol: str,
) -> dict[datetime, _TradeBar]:
    if not candles:
        return {}
    start = min(candle.timestamp for candle in candles)
    end = max(candle.timestamp for candle in candles) + timedelta(minutes=5)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(_TRADE_BAR_SQL, [symbol, start, end]).fetchall()
    return {
        _as_utc(row[0]): _TradeBar(
            *(float(value) for value in row[1:6]),
            tuple(float(value) for value in row[6]),
            tuple(float(value) for value in row[7]),
        )
        for row in rows
    }


def _bar_comparison(
    candle: LedgerCandle,
    trade: _TradeBar,
) -> dict[str, object]:
    backend = (candle.open, candle.high, candle.low, candle.close, candle.volume)
    recorded = (trade.open, trade.high, trade.low, trade.close, trade.volume)
    names = ("open", "high", "low", "close", "volume")
    differences = {
        name: abs(backend[index] - recorded[index]) for index, name in enumerate(names)
    }
    exact = all(value <= _FLOAT_TOLERANCE for value in differences.values())
    equivalent = _venue_equivalent(candle, trade, differences)
    return {
        "feed_ts": candle.timestamp.isoformat(),
        "exact_ohlcv": exact,
        "venue_equivalent_ohlcv": equivalent,
        "boundary_ambiguous": equivalent and not exact,
        "backend": dict(zip(names, backend, strict=True)),
        "recorded_trades": dict(zip(names, recorded, strict=True)),
        "boundary_candidates": {
            "open": list(trade.open_candidates),
            "close": list(trade.close_candidates),
        },
        "absolute_difference": differences,
    }


def _venue_equivalent(
    candle: LedgerCandle,
    trade: _TradeBar,
    differences: Mapping[str, float],
) -> bool:
    interior_matches = all(
        differences[name] <= _FLOAT_TOLERANCE for name in ("high", "low", "volume")
    )
    return (
        interior_matches
        and _matches_candidate(candle.open, trade.open_candidates)
        and _matches_candidate(candle.close, trade.close_candidates)
    )


def _matches_candidate(value: float, candidates: Sequence[float]) -> bool:
    return any(abs(value - candidate) <= _FLOAT_TOLERANCE for candidate in candidates)


def _maximum_differences(
    comparisons: Sequence[Mapping[str, object]],
) -> dict[str, float | None]:
    names = ("open", "high", "low", "close", "volume")
    if not comparisons:
        return dict.fromkeys(names)
    return {
        name: max(_comparison_difference(item, name) for item in comparisons)
        for name in names
    }


def _comparison_difference(item: Mapping[str, object], name: str) -> float:
    differences = item.get("absolute_difference")
    if not isinstance(differences, Mapping):
        raise RuntimeError("invalid internal candle comparison")
    return _finite_number(differences.get(name), f"{name} difference")


def _as_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RuntimeError("research database returned a timezone-naive bar timestamp")
    return value.astimezone(UTC)


_TRADE_BAR_SQL = """
WITH filtered AS (
    SELECT
        time_bucket(
            INTERVAL '5 minutes',
            to_timestamp(CAST(exchange_ts_ms AS DOUBLE) / 1000.0)
        ) AS bar_open_at,
        exchange_ts_ms,
        trade_id,
        price,
        size
    FROM replay_live_public_trades
    WHERE symbol = ?
      AND exchange_ts_ms >= epoch_ms(CAST(? AS TIMESTAMPTZ))
      AND exchange_ts_ms < epoch_ms(CAST(? AS TIMESTAMPTZ))
), bounded AS (
    SELECT
        *,
        min(exchange_ts_ms) OVER (PARTITION BY bar_open_at) AS first_ms,
        max(exchange_ts_ms) OVER (PARTITION BY bar_open_at) AS last_ms
    FROM filtered
)
SELECT
    bar_open_at,
    first(price ORDER BY exchange_ts_ms, trade_id) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price ORDER BY exchange_ts_ms, trade_id) AS close,
    sum(size) AS volume,
    list(DISTINCT price ORDER BY price) FILTER (
        WHERE exchange_ts_ms = first_ms
    ) AS open_candidates,
    list(DISTINCT price ORDER BY price) FILTER (
        WHERE exchange_ts_ms = last_ms
    ) AS close_candidates
FROM bounded
GROUP BY bar_open_at
ORDER BY bar_open_at
"""


def l2_quality(
    database_path: Path,
    candles: Sequence[LedgerCandle],
    symbol: str,
) -> dict[str, object]:
    """Measure per-candle L2 continuity without creating a strategy gate."""
    books, gaps = _load_l2_evidence(database_path, candles, symbol)
    by_bar = [_bar_l2_quality(candle, books, gaps) for candle in candles]
    return {
        "database_path": str(database_path.resolve()),
        "diagnostic_gap_threshold_seconds": _L2_GAP_THRESHOLD_SECONDS,
        **_l2_counts(by_bar),
        "by_event_type": {
            event_type: _l2_counts(
                [
                    row
                    for candle, row in zip(candles, by_bar, strict=True)
                    if candle.event_type == event_type
                ]
            )
            for event_type in sorted({candle.event_type for candle in candles})
        },
        "by_bar": by_bar,
    }


def _l2_counts(rows: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return {
        "bars": len(rows),
        "continuous_l2_bars": sum(row["continuous_l2"] is True for row in rows),
        "quality_usable_bars": sum(row["quality_usable"] is True for row in rows),
        "negative_receive_lag_rows": sum(
            int(row["negative_receive_lag_rows"]) for row in rows
        ),
        "explicit_stream_gaps": sum(int(row["explicit_stream_gaps"]) for row in rows),
    }


def _load_l2_evidence(
    database_path: Path,
    candles: Sequence[LedgerCandle],
    symbol: str,
) -> tuple[list[tuple[int, int]], list[tuple[int | None, int | None]]]:
    if not candles:
        return [], []
    start_ms = _timestamp_ms(min(candle.timestamp for candle in candles))
    end_ms = (
        _timestamp_ms(max(candle.timestamp for candle in candles)) + _FIVE_MINUTES_MS
    )
    with duckdb.connect(str(database_path), read_only=True) as connection:
        books = connection.execute(
            _L2_ROWS_SQL,
            [symbol, start_ms, end_ms],
        ).fetchall()
        gaps = connection.execute(
            _GAP_ROWS_SQL,
            [symbol, start_ms, end_ms],
        ).fetchall()
    return (
        [(int(row[0]), int(row[1])) for row in books],
        [(_optional_int(row[0]), _optional_int(row[1])) for row in gaps],
    )


def _bar_l2_quality(
    candle: LedgerCandle,
    books: Sequence[tuple[int, int]],
    gaps: Sequence[tuple[int | None, int | None]],
) -> dict[str, object]:
    start_ms = _timestamp_ms(candle.timestamp)
    end_ms = start_ms + _FIVE_MINUTES_MS
    selected = [row for row in books if start_ms <= row[0] < end_ms]
    exchange_times = [row[0] for row in selected]
    negative_lags = sum(
        received < exchange * 1_000_000 for exchange, received in selected
    )
    explicit_gaps = sum(_gap_overlaps(gap, start_ms, end_ms) for gap in gaps)
    first_gap = None if not exchange_times else (exchange_times[0] - start_ms) / 1_000.0
    end_gap = None if not exchange_times else (end_ms - exchange_times[-1]) / 1_000.0
    maximum_gap = _maximum_exchange_gap(exchange_times)
    continuous = _continuous_l2(first_gap, end_gap, maximum_gap)
    return {
        "feed_ts": candle.timestamp.isoformat(),
        "snapshot_count": len(selected),
        "start_boundary_gap_seconds": first_gap,
        "end_boundary_gap_seconds": end_gap,
        "maximum_exchange_gap_seconds": maximum_gap,
        "negative_receive_lag_rows": negative_lags,
        "explicit_stream_gaps": explicit_gaps,
        "continuous_l2": continuous,
        "quality_usable": continuous and not negative_lags and not explicit_gaps,
    }


def _continuous_l2(
    start_gap: float | None,
    end_gap: float | None,
    maximum_gap: float | None,
) -> bool:
    values = (start_gap, end_gap, maximum_gap)
    return all(
        value is not None and value <= _L2_GAP_THRESHOLD_SECONDS for value in values
    )


def _maximum_exchange_gap(exchange_times: Sequence[int]) -> float | None:
    if not exchange_times:
        return None
    if len(exchange_times) == 1:
        return 0.0
    return (
        max(current - previous for previous, current in pairwise(exchange_times))
        / 1_000.0
    )


def _gap_overlaps(
    gap: tuple[int | None, int | None],
    start_ms: int,
    end_ms: int,
) -> bool:
    previous, following = gap
    gap_start = previous if previous is not None else following
    gap_end = following if following is not None else previous
    return (
        gap_start is not None
        and gap_end is not None
        and gap_end >= start_ms
        and gap_start < end_ms
    )


def _timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError("research database returned an invalid gap timestamp")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


_L2_ROWS_SQL = """
SELECT exchange_ts_ms, received_ts_ns
FROM replay_live_book_snapshots
WHERE symbol = ? AND exchange_ts_ms >= ? AND exchange_ts_ms < ?
ORDER BY exchange_ts_ms, received_ts_ns
"""


_GAP_ROWS_SQL = """
SELECT previous_exchange_ts_ms, next_exchange_ts_ms
FROM live_stream_gaps
WHERE symbol = ?
  AND coalesce(next_exchange_ts_ms, previous_exchange_ts_ms) >= ?
  AND coalesce(previous_exchange_ts_ms, next_exchange_ts_ms) < ?
ORDER BY detected_ts_ns
"""
