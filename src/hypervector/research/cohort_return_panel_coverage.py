"""Report-only synchronized bar coverage for a candidate cohort roster."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import duckdb

_TABLE = "canonical_trade_5m_bars"
_REQUIRED_COLUMNS = frozenset({"symbol", "bar_open_at", "close"})


def build_return_panel_coverage_report(
    connection: duckdb.DuckDBPyConnection,
    symbols: Sequence[str],
) -> dict[str, object]:
    """Audit exact shared timestamps without estimating returns or weights."""
    roster = _roster(symbols)
    _require_source_schema(connection)
    placeholders = ",".join("?" for _ in roster)
    rows = connection.execute(
        f"""
        SELECT symbol,
               count(*) AS bar_count,
               count(DISTINCT bar_open_at) AS distinct_bar_count,
               min(bar_open_at) AS first_bar,
               max(bar_open_at) AS last_bar
        FROM {_TABLE}
        WHERE symbol IN ({placeholders})
        GROUP BY symbol
        ORDER BY symbol
        """,
        list(roster),
    ).fetchall()
    by_symbol = _symbol_rows(roster, rows)
    duplicates = sum(
        int(row["bar_count"]) - int(row["distinct_bar_count"])
        for row in by_symbol.values()
    )
    if duplicates:
        raise ValueError(
            f"canonical trade bars contain {duplicates} duplicate symbol/timestamp rows"
        )
    common_count, common_start, common_end = connection.execute(
        f"""
        WITH selected AS (
            SELECT symbol, bar_open_at
            FROM {_TABLE}
            WHERE symbol IN ({placeholders})
        ), shared AS (
            SELECT bar_open_at
            FROM selected
            GROUP BY bar_open_at
            HAVING count(DISTINCT symbol) = ?
        )
        SELECT count(*), min(bar_open_at), max(bar_open_at)
        FROM shared
        """,
        [*roster, len(roster)],
    ).fetchone()
    missing = [symbol for symbol in roster if by_symbol[symbol]["bar_count"] == 0]
    constructible = not missing and int(common_count) > 0
    return {
        "schema_version": 1,
        "mode": "cohort_return_panel_coverage_v1",
        "status": (
            "synchronized_panel_constructible"
            if constructible
            else "insufficient_synchronized_coverage"
        ),
        "contract": _contract(),
        "source_table": _TABLE,
        "requested_symbols": list(roster),
        "missing_symbols": missing,
        "by_symbol": by_symbol,
        "common_timestamp_count": int(common_count),
        "common_start_utc": _utc_text(common_start),
        "common_end_utc": _utc_text(common_end),
        "covariance_weighting_status": (
            "coverage_only_not_qualified" if constructible else "withheld"
        ),
        "limitations": _limitations(),
    }


def _roster(symbols: Sequence[str]) -> tuple[str, ...]:
    roster = tuple(_symbol(value) for value in symbols)
    if not roster:
        raise ValueError("candidate roster must not be empty")
    if len(set(roster)) != len(roster):
        raise ValueError("candidate roster contains duplicate symbols")
    return roster


def _symbol(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("candidate symbols must be non-empty text")
    return value.strip()


def _require_source_schema(connection: duckdb.DuckDBPyConnection) -> None:
    exists = connection.execute(
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        [_TABLE],
    ).fetchone()[0]
    if exists != 1:
        raise ValueError(f"missing required table: {_TABLE}")
    columns = {
        str(row[0]) for row in connection.execute(f"DESCRIBE {_TABLE}").fetchall()
    }
    missing = sorted(_REQUIRED_COLUMNS - columns)
    if missing:
        raise ValueError(f"{_TABLE} missing required columns: {missing}")


def _symbol_rows(
    roster: tuple[str, ...],
    rows: list[tuple[object, ...]],
) -> dict[str, dict[str, object]]:
    observed = {
        str(symbol): {
            "bar_count": int(count),
            "distinct_bar_count": int(distinct_count),
            "first_bar_utc": _utc_text(first),
            "last_bar_utc": _utc_text(last),
        }
        for symbol, count, distinct_count, first, last in rows
    }
    return {
        symbol: observed.get(
            symbol,
            {
                "bar_count": 0,
                "distinct_bar_count": 0,
                "first_bar_utc": None,
                "last_bar_utc": None,
            },
        )
        for symbol in roster
    }


def _utc_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("bar timestamp must be a datetime")
    if value.tzinfo is None:
        raise ValueError("bar timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "covariance_weights_generated": False,
    }


def _limitations() -> list[str]:
    return [
        "shared timestamps establish data availability, not a stable covariance model",
        "session calendars and no-trade bars require explicit point-in-time treatment",
        "coverage does not estimate expectancy or authorize portfolio weights",
        "no live profile, route authority, or sizing is changed",
    ]
