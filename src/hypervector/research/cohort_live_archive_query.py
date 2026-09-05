"""Resource-bounded SQL plan for durable cohort lifecycle accounting."""

from __future__ import annotations

import duckdb

_TABLES = (
    (
        "archive_cohort_run_profiles",
        """
        SELECT run_id, min(profile_fingerprint) AS profile_fingerprint
        FROM cohort_live_events
        WHERE ledger_symbol = 'PORTFOLIO'
        GROUP BY run_id
        HAVING count(DISTINCT profile_fingerprint) = 1
        """,
    ),
    (
        "archive_attributed_fills",
        "SELECT * FROM cohort_live_attributed_fills",
    ),
    (
        "archive_entry_fills",
        """
        SELECT symbol, venue_timestamp_ms, any_value(oid) AS entry_oid,
               any_value(origin_run_id) AS entry_run_id,
               any_value(strategy_id) AS strategy_id,
               any_value(direction) AS direction
        FROM archive_attributed_fills WHERE operation = 'entry'
        GROUP BY symbol, venue_timestamp_ms
        """,
    ),
    (
        "archive_entry_acknowledgements",
        """
        SELECT ledger_symbol AS symbol, source_path, run_id,
               min(sequence) AS sequence, profile_fingerprint,
               CAST(json_extract_string(payload, '$.oid') AS UBIGINT) AS entry_oid
        FROM cohort_live_events
        WHERE event_type = 'order_acknowledgement'
          AND json_extract_string(payload, '$.operation') = 'entry'
          AND CAST(json_extract_string(payload, '$.accepted') AS BOOLEAN) = TRUE
        GROUP BY ledger_symbol, source_path, run_id, profile_fingerprint, entry_oid
        """,
    ),
    (
        "archive_open_position_events",
        """
        SELECT source_path, run_id, sequence,
               CAST(json_extract_string(
                   payload, '$.margin_used_usd') AS DOUBLE) AS margin_used_usd,
               CAST(json_extract_string(
                   payload, '$.leverage') AS DOUBLE) AS leverage
        FROM cohort_live_events
        WHERE event_type = 'position'
          AND abs(CAST(json_extract_string(
              payload, '$.size_signed') AS DOUBLE)) > 0.0
        """,
    ),
    (
        "archive_entry_position_sequences",
        """
        SELECT entry.symbol, entry.venue_timestamp_ms, entry.entry_oid,
               acknowledgement.source_path, acknowledgement.run_id,
               acknowledgement.profile_fingerprint,
               position.sequence AS position_sequence
        FROM archive_entry_fills AS entry
        JOIN archive_entry_acknowledgements AS acknowledgement
          ON acknowledgement.symbol = entry.symbol
         AND acknowledgement.run_id = entry.entry_run_id
         AND acknowledgement.entry_oid = entry.entry_oid
        ASOF JOIN archive_open_position_events AS position
          ON acknowledgement.source_path = position.source_path
         AND position.run_id = acknowledgement.run_id
         AND acknowledgement.sequence < position.sequence
        """,
    ),
    (
        "archive_entry_positions",
        """
        SELECT sequence.symbol, sequence.venue_timestamp_ms, sequence.entry_oid,
               sequence.profile_fingerprint,
               position.margin_used_usd, position.leverage
        FROM archive_entry_position_sequences AS sequence
        JOIN archive_open_position_events AS position
          ON position.source_path = sequence.source_path
         AND position.run_id = sequence.run_id
         AND position.sequence = sequence.position_sequence
        """,
    ),
    (
        "archive_close_orders",
        """
        WITH closes AS (
            SELECT * FROM archive_attributed_fills
            WHERE starts_with(direction, 'Close')
        )
        SELECT close.symbol,
               coalesce(any_value(entry.strategy_id),
                        any_value(close.strategy_id)) AS strategy_id,
               any_value(entry.entry_run_id) AS entry_run_id,
               close.entry_venue_timestamp_ms, close.oid AS exit_oid,
               any_value(entry.direction) AS entry_direction,
               max(close.lifecycle_fees_usd) AS lifecycle_fees_usd,
               max(close.lifecycle_funding_usd) AS lifecycle_funding_usd,
               max(close.lifecycle_net_pnl_usd) AS lifecycle_net_pnl_usd
        FROM closes AS close
        LEFT JOIN archive_entry_fills AS entry
          ON entry.symbol = close.symbol
         AND entry.venue_timestamp_ms = close.entry_venue_timestamp_ms
        GROUP BY close.symbol, close.entry_venue_timestamp_ms, close.oid
        """,
    ),
    (
        "archive_exit_fills",
        """
        SELECT symbol, oid AS exit_oid,
               max(venue_timestamp_ms) AS exit_venue_timestamp_ms
        FROM archive_attributed_fills WHERE operation != 'entry'
        GROUP BY symbol, oid
        """,
    ),
)

_SELECT = """
SELECT close.symbol, close.strategy_id, close.entry_run_id,
       close.entry_direction, close.lifecycle_net_pnl_usd,
       close.lifecycle_fees_usd, close.lifecycle_funding_usd,
       position.margin_used_usd, position.leverage,
       cohort.profile_fingerprint, position.entry_oid,
       exit.exit_venue_timestamp_ms
FROM archive_close_orders AS close
LEFT JOIN archive_entry_positions AS position
  ON position.symbol = close.symbol
 AND position.venue_timestamp_ms = close.entry_venue_timestamp_ms
LEFT JOIN archive_cohort_run_profiles AS cohort
  ON cohort.run_id = close.entry_run_id
LEFT JOIN archive_exit_fills AS exit
  ON exit.symbol = close.symbol AND exit.exit_oid = close.exit_oid
ORDER BY exit.exit_venue_timestamp_ms, close.symbol, close.exit_oid
"""


def load_archive_lifecycle_rows(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[tuple[object, ...], ...]:
    """Materialize bounded intermediates and return exact lifecycle rows."""
    for table, query in _TABLES:
        connection.execute(f"CREATE TEMP TABLE {table} AS {query}")
    rows = connection.execute(_SELECT).fetchall()
    return tuple(tuple(row) for row in rows)
