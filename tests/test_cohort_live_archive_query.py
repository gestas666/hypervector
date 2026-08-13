"""Resource-bounded lifecycle projection tests for the live portfolio archive."""

from __future__ import annotations

import duckdb

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
            "profile-a",
            11,
            2_000,
        ),
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
          ('BTC','btc.jsonl','run-1',10,'profile-a','order_acknowledgement',
           '{"operation":"entry","accepted":true,"oid":11}'),
          ('BTC','btc.jsonl','run-1',11,'profile-a','position',
           '{"size_signed":1.0,"margin_used_usd":5.0,"leverage":5.0}'),
          ('BTC','btc.jsonl','run-1',12,'profile-a','position',
           '{"size_signed":1.0,"margin_used_usd":7.0,"leverage":5.0}');
        """
    )
