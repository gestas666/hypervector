"""DuckDB schema and ingestion SQL for live Hyperliquid event evidence."""

LIVE_EVENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS live_event_files (
    file_id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    utc_date DATE NOT NULL,
    dataset VARCHAR NOT NULL,
    source_path VARCHAR NOT NULL,
    byte_count BIGINT NOT NULL,
    row_count BIGINT NOT NULL,
    sha256 VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    UNIQUE (source_path),
    CHECK (dataset IN ('l2', 'trades', 'asset_context', 'gaps'))
);
CREATE TABLE IF NOT EXISTS live_book_snapshots (
    symbol VARCHAR NOT NULL,
    exchange_ts_ms BIGINT NOT NULL,
    received_ts_ns BIGINT NOT NULL,
    bids STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[] NOT NULL,
    asks STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[] NOT NULL,
    source VARCHAR NOT NULL,
    file_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS live_public_trades (
    symbol VARCHAR NOT NULL,
    aggressor_side VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    size DOUBLE NOT NULL,
    transaction_hash VARCHAR NOT NULL,
    exchange_ts_ms BIGINT NOT NULL,
    received_ts_ns BIGINT NOT NULL,
    trade_id BIGINT NOT NULL,
    buyer VARCHAR NOT NULL,
    seller VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    file_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS live_asset_contexts (
    symbol VARCHAR NOT NULL,
    observed_ts_ms BIGINT NOT NULL,
    received_ts_ns BIGINT NOT NULL,
    mark_price DOUBLE NOT NULL,
    oracle_price DOUBLE NOT NULL,
    funding_rate_hourly DOUBLE NOT NULL,
    open_interest DOUBLE NOT NULL,
    mid_price DOUBLE,
    timestamp_source VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    file_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS live_stream_gaps (
    symbol VARCHAR NOT NULL,
    channel VARCHAR NOT NULL,
    detected_ts_ns BIGINT NOT NULL,
    reason VARCHAR NOT NULL,
    previous_exchange_ts_ms BIGINT,
    next_exchange_ts_ms BIGINT,
    file_id VARCHAR NOT NULL
);
CREATE OR REPLACE VIEW replay_live_public_trades AS
SELECT * FROM live_public_trades
QUALIFY row_number() OVER (
    PARTITION BY symbol, trade_id
    ORDER BY received_ts_ns, file_id
) = 1;
CREATE OR REPLACE VIEW replay_live_book_snapshots AS
SELECT * FROM live_book_snapshots
QUALIFY row_number() OVER (
    PARTITION BY symbol, exchange_ts_ms, bids, asks, source
    ORDER BY received_ts_ns, file_id
) = 1;
CREATE OR REPLACE VIEW canonical_public_trades AS
WITH combined AS (
    SELECT
        symbol,
        trade_id,
        ts_exchange_ms AS exchange_ts_ms,
        ts_utc,
        aggressor_side,
        price,
        size,
        source,
        'archive' AS source_origin,
        0 AS source_priority
    FROM replay_public_trades
    UNION ALL
    SELECT
        symbol,
        trade_id,
        exchange_ts_ms,
        to_timestamp(CAST(exchange_ts_ms AS DOUBLE) / 1000.0) AS ts_utc,
        aggressor_side,
        price,
        size,
        source,
        'live' AS source_origin,
        1 AS source_priority
    FROM replay_live_public_trades
)
SELECT * EXCLUDE (source_priority)
FROM combined
QUALIFY row_number() OVER (
    PARTITION BY symbol, trade_id
    ORDER BY source_priority
) = 1;
CREATE OR REPLACE VIEW canonical_trade_1m_bars AS
SELECT
    symbol,
    time_bucket(INTERVAL '1 minute', ts_utc) AS bar_open_at,
    first(price ORDER BY exchange_ts_ms, trade_id) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price ORDER BY exchange_ts_ms, trade_id) AS close,
    sum(size) AS volume,
    count(*) AS trade_count
FROM canonical_public_trades
GROUP BY symbol, time_bucket(INTERVAL '1 minute', ts_utc);
CREATE OR REPLACE VIEW canonical_trade_5m_bars AS
SELECT
    symbol,
    time_bucket(INTERVAL '5 minutes', bar_open_at) AS bar_open_at,
    first(open ORDER BY bar_open_at) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close ORDER BY bar_open_at) AS close,
    sum(volume) AS volume,
    sum(trade_count) AS trade_count
FROM canonical_trade_1m_bars
GROUP BY symbol, time_bucket(INTERVAL '5 minutes', bar_open_at);
"""

LIVE_L2_INSERT_SQL = """
INSERT INTO live_book_snapshots
SELECT
    raw.symbol,
    raw.exchange_ts_ms,
    raw.received_ts_ns,
    list_transform(
        raw.bids,
        level -> struct_pack(
            n := CAST(level.order_count AS INTEGER),
            px := CAST(level.price AS DOUBLE),
            sz := CAST(level.size AS DOUBLE)
        )
    ),
    list_transform(
        raw.asks,
        level -> struct_pack(
            n := CAST(level.order_count AS INTEGER),
            px := CAST(level.price AS DOUBLE),
            sz := CAST(level.size AS DOUBLE)
        )
    ),
    raw.source,
    files.file_id
FROM read_parquet(?, filename = true) AS raw
INNER JOIN incoming_live_files AS files ON raw.filename = files.source_path
WHERE files.dataset = 'l2'
"""

LIVE_TRADE_INSERT_SQL = """
INSERT INTO live_public_trades
SELECT
    raw.symbol,
    raw.aggressor_side,
    raw.price,
    raw.size,
    raw.transaction_hash,
    raw.exchange_ts_ms,
    raw.received_ts_ns,
    raw.trade_id,
    raw.buyer,
    raw.seller,
    raw.source,
    files.file_id
FROM read_parquet(?, filename = true) AS raw
INNER JOIN incoming_live_files AS files ON raw.filename = files.source_path
WHERE files.dataset = 'trades'
"""

LIVE_CONTEXT_INSERT_SQL = """
INSERT INTO live_asset_contexts
SELECT
    raw.symbol,
    raw.observed_ts_ms,
    raw.received_ts_ns,
    raw.mark_price,
    raw.oracle_price,
    raw.funding_rate_hourly,
    raw.open_interest,
    raw.mid_price,
    raw.timestamp_source,
    raw.source,
    files.file_id
FROM read_parquet(?, filename = true) AS raw
INNER JOIN incoming_live_files AS files ON raw.filename = files.source_path
WHERE files.dataset = 'asset_context'
"""
