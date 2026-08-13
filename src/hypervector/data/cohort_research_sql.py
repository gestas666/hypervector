"""DuckDB schema for authoritative multi-asset live cohort journals."""

COHORT_LIVE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cohort_live_sources (
    source_path VARCHAR PRIMARY KEY,
    ledger_symbol VARCHAR NOT NULL,
    imported_bytes UBIGINT NOT NULL,
    prefix_sha256 VARCHAR NOT NULL,
    imported_rows UBIGINT NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS cohort_live_events (
    event_id VARCHAR PRIMARY KEY,
    source_path VARCHAR NOT NULL,
    ledger_symbol VARCHAR NOT NULL,
    schema_version INTEGER NOT NULL,
    sequence UBIGINT NOT NULL,
    event_type VARCHAR NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    execution_mode VARCHAR NOT NULL,
    effective_mode VARCHAR NOT NULL,
    live_armed BOOLEAN NOT NULL,
    execution_authority VARCHAR NOT NULL,
    profile_id VARCHAR NOT NULL,
    profile_fingerprint VARCHAR NOT NULL,
    run_fingerprint VARCHAR NOT NULL,
    run_id VARCHAR NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (source_path, run_id, sequence)
);

CREATE OR REPLACE VIEW cohort_live_fills AS
SELECT
    event_id,
    ledger_symbol AS symbol,
    run_id,
    sequence,
    observed_at_utc,
    CAST(json_extract_string(payload, '$.oid') AS UBIGINT) AS oid,
    CAST(json_extract_string(payload, '$.trade_id') AS UBIGINT) AS trade_id,
    CAST(json_extract_string(payload, '$.venue_timestamp_ms') AS UBIGINT)
        AS venue_timestamp_ms,
    CAST(json_extract_string(payload, '$.price') AS DOUBLE) AS price,
    CAST(json_extract_string(payload, '$.size') AS DOUBLE) AS size,
    json_extract_string(payload, '$.side') AS side,
    json_extract_string(payload, '$.direction') AS direction,
    CAST(json_extract_string(payload, '$.closed_pnl_usd') AS DOUBLE)
        AS closed_pnl_usd,
    CAST(json_extract_string(payload, '$.fee_usd') AS DOUBLE) AS fee_usd
FROM cohort_live_events
WHERE event_type = 'fill';

CREATE OR REPLACE VIEW cohort_live_closed_fills AS
SELECT *
FROM cohort_live_fills
WHERE starts_with(direction, 'Close');

CREATE OR REPLACE VIEW cohort_live_attributed_fills AS
WITH expanded AS (
    SELECT
        event_id AS snapshot_event_id,
        observed_at_utc AS snapshot_observed_at_utc,
        CAST(json_extract_string(fill.value, '$.trade_id') AS UBIGINT)
            AS trade_id,
        json_extract_string(fill.value, '$.symbol') AS symbol,
        json_extract_string(fill.value, '$.strategy_id') AS strategy_id,
        json_extract_string(fill.value, '$.exit_controller_id')
            AS exit_controller_id,
        json_extract_string(fill.value, '$.origin_run_id') AS origin_run_id,
        json_extract_string(fill.value, '$.operation') AS operation,
        CAST(json_extract_string(fill.value, '$.oid') AS UBIGINT) AS oid,
        CAST(json_extract_string(fill.value, '$.venue_timestamp_ms') AS UBIGINT)
            AS venue_timestamp_ms,
        CAST(json_extract_string(fill.value, '$.price') AS DOUBLE) AS price,
        CAST(json_extract_string(fill.value, '$.size') AS DOUBLE) AS size,
        json_extract_string(fill.value, '$.side') AS side,
        json_extract_string(fill.value, '$.direction') AS direction,
        CAST(json_extract_string(fill.value, '$.fee_usd') AS DOUBLE) AS fee_usd,
        CAST(json_extract_string(fill.value, '$.closed_pnl_usd') AS DOUBLE)
            AS closed_pnl_usd,
        CAST(json_extract_string(fill.value, '$.expected_price') AS DOUBLE)
            AS expected_price,
        CAST(json_extract_string(fill.value, '$.slippage_bps') AS DOUBLE)
            AS slippage_bps,
        CAST(json_extract_string(fill.value, '$.acknowledgement_latency_ms') AS UBIGINT)
            AS acknowledgement_latency_ms,
        CAST(json_extract_string(fill.value, '$.markout_bps') AS DOUBLE)
            AS markout_bps,
        CAST(json_extract_string(fill.value, '$.markout_horizon_ms') AS UBIGINT)
            AS markout_horizon_ms,
        json_extract_string(fill.value, '$.exit_reason') AS exit_reason,
        CAST(json_extract_string(fill.value, '$.lifecycle_fees_usd') AS DOUBLE)
            AS lifecycle_fees_usd,
        CAST(json_extract_string(fill.value, '$.lifecycle_funding_usd') AS DOUBLE)
            AS lifecycle_funding_usd,
        CAST(json_extract_string(fill.value, '$.net_pnl_usd') AS DOUBLE)
            AS lifecycle_net_pnl_usd,
        CAST(json_extract_string(fill.value, '$.holding_time_ms') AS UBIGINT)
            AS holding_time_ms,
        CAST(json_extract_string(fill.value, '$.entry_price') AS DOUBLE)
            AS entry_price,
        CAST(json_extract_string(fill.value, '$.entry_venue_timestamp_ms') AS UBIGINT)
            AS entry_venue_timestamp_ms
    FROM cohort_live_events AS event,
         json_each(event.payload, '$.recent_fills') AS fill
    WHERE event.event_type = 'cohort_snapshot'
), ranked AS (
    SELECT *, row_number() OVER (
        PARTITION BY symbol, trade_id
        ORDER BY snapshot_observed_at_utc DESC, snapshot_event_id DESC
    ) AS snapshot_rank
    FROM expanded
)
SELECT * EXCLUDE (snapshot_rank)
FROM ranked
WHERE snapshot_rank = 1;

CREATE OR REPLACE VIEW cohort_live_close_orders AS
WITH entries AS (
    SELECT
        symbol,
        venue_timestamp_ms,
        any_value(strategy_id) AS strategy_id,
        any_value(origin_run_id) AS origin_run_id,
        any_value(direction) AS direction,
        sum(size) AS entry_size,
        sum(price * size) / sum(size) AS entry_price
    FROM cohort_live_attributed_fills
    WHERE operation = 'entry'
    GROUP BY symbol, venue_timestamp_ms
), closes AS (
    SELECT *
    FROM cohort_live_attributed_fills
    WHERE starts_with(direction, 'Close')
)
SELECT
    close.symbol,
    coalesce(any_value(entry.strategy_id), any_value(close.strategy_id))
        AS strategy_id,
    any_value(close.exit_controller_id) AS exit_controller_id,
    any_value(entry.origin_run_id) AS entry_run_id,
    any_value(close.origin_run_id) AS exit_run_id,
    close.entry_venue_timestamp_ms,
    close.oid AS exit_oid,
    any_value(entry.direction) AS entry_direction,
    coalesce(max(close.entry_price), any_value(entry.entry_price)) AS entry_price,
    sum(close.price * close.size) / sum(close.size) AS exit_price,
    sum(close.size) AS exit_size,
    sum(close.closed_pnl_usd) AS closed_pnl_usd,
    sum(close.fee_usd) AS exit_fee_usd,
    max(close.lifecycle_fees_usd) AS lifecycle_fees_usd,
    max(close.lifecycle_funding_usd) AS lifecycle_funding_usd,
    max(close.lifecycle_net_pnl_usd) AS lifecycle_net_pnl_usd,
    max(close.holding_time_ms) AS holding_time_ms,
    coalesce(any_value(close.exit_reason), any_value(close.operation))
        AS exit_reason,
    count(*) AS exit_fill_count
FROM closes AS close
LEFT JOIN entries AS entry
    ON entry.symbol = close.symbol
    AND entry.venue_timestamp_ms = close.entry_venue_timestamp_ms
GROUP BY close.symbol, close.entry_venue_timestamp_ms, close.oid;
"""
