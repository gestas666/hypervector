"""Resource-bounded lifecycle projection tests for the live portfolio archive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import duckdb

from hypervector.data.cohort_research_sql import COHORT_LIVE_SCHEMA_SQL
from hypervector.research.cohort_live_archive_query import load_archive_lifecycle_rows


def test_archive_query_uses_first_nonzero_position_after_entry_ack() -> None:
    connection = duckdb.connect(":memory:")
    _create_tables(connection)
    _insert_lifecycle(connection)

    rows = load_archive_lifecycle_rows(connection)

    assert rows == (
        (
            "BTC",
            "alpha",
            "run-1",
            "Open Long",
            1.2,
            0.2,
            0.1,
            5.0,
            5.0,
            "cohort-profile",
            11,
            2_000,
        ),
    )


def test_attributed_fill_expands_each_distinct_recent_fill_array_once() -> None:
    """Unrelated snapshot changes must not repeatedly expand identical fills."""
    connection = duckdb.connect(":memory:")
    connection.execute(COHORT_LIVE_SCHEMA_SQL)
    started = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [_snapshot_row(index, started) for index in range(100)]
    connection.executemany(
        "INSERT INTO cohort_live_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )

    plan = "\n".join(
        row[1]
        for row in connection.execute(
            "EXPLAIN ANALYZE SELECT * FROM cohort_live_attributed_fills"
        ).fetchall()
    )
    json_each = plan[
        plan.index("INOUT_FUNCTION") : plan.index(
            "PROJECTION", plan.index("INOUT_FUNCTION")
        )
    ]
    attributed = connection.execute(
        "SELECT snapshot_event_id, trade_id FROM cohort_live_attributed_fills"
    ).fetchall()

    assert "100 rows" not in json_each
    assert "1 row" in json_each
    assert attributed == [("event-99", 1)]
    connection.execute(
        "INSERT INTO cohort_live_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        _snapshot_row(100, started, strategy_id="beta"),
    )
    latest_revision = connection.execute(
        "SELECT snapshot_event_id, strategy_id FROM cohort_live_attributed_fills"
    ).fetchall()
    assert latest_revision == [("event-100", "beta")]


def _snapshot_row(
    index: int,
    started: datetime,
    *,
    strategy_id: str = "alpha",
) -> tuple[object, ...]:
    payload = json.dumps(
        {
            "heartbeat": index,
            "recent_fills": [
                {"trade_id": 1, "symbol": "BTC", "strategy_id": strategy_id}
            ],
        }
    )
    return (
        f"event-{index}",
        "decisions.jsonl",
        "PORTFOLIO",
        1,
        index,
        "cohort_snapshot",
        started + timedelta(seconds=index),
        "live",
        "live",
        True,
        "live",
        "profile",
        "fingerprint",
        "run-fingerprint",
        "run-1",
        payload,
    )


def _create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE cohort_live_attributed_fills (
            symbol VARCHAR, strategy_id VARCHAR, origin_run_id VARCHAR,
            operation VARCHAR, oid UBIGINT, venue_timestamp_ms UBIGINT,
            price DOUBLE, size DOUBLE, direction VARCHAR,
            lifecycle_fees_usd DOUBLE, lifecycle_funding_usd DOUBLE,
            lifecycle_net_pnl_usd DOUBLE, entry_venue_timestamp_ms UBIGINT
        );
        CREATE TABLE cohort_live_events (
            ledger_symbol VARCHAR, source_path VARCHAR, run_id VARCHAR,
            sequence UBIGINT, profile_fingerprint VARCHAR,
            event_type VARCHAR, payload JSON
        );
        """
    )


def _insert_lifecycle(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        INSERT INTO cohort_live_attributed_fills VALUES
          ('BTC','alpha','run-1','entry',11,1000,100.0,1.0,'Open Long',NULL,NULL,NULL,NULL),
          ('BTC','alpha','run-1','maximum_hold',22,2000,101.5,1.0,'Close Long',0.2,0.1,1.2,1000);
        INSERT INTO cohort_live_events VALUES
          ('PORTFOLIO','decisions.jsonl','run-1',1,'cohort-profile','cohort_snapshot',
           '{}'),
          ('BTC','btc.jsonl','run-1',10,'profile-a','order_acknowledgement',
           '{"operation":"entry","accepted":true,"oid":11}'),
          ('BTC','btc.jsonl','run-1',11,'profile-a','position',
           '{"size_signed":1.0,"margin_used_usd":5.0,"leverage":5.0}'),
          ('BTC','btc.jsonl','run-1',12,'profile-a','position',
           '{"size_signed":1.0,"margin_used_usd":7.0,"leverage":5.0}');
        """
    )
