"""DuckDB schema and bulk-ingestion SQL for the research market store."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS archive_bundles (
    bundle_id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    start_utc TIMESTAMPTZ NOT NULL,
    end_utc TIMESTAMPTZ NOT NULL,
    depth INTEGER NOT NULL,
    book_rows BIGINT NOT NULL,
    trade_rows BIGINT NOT NULL,
    book_manifest_sha256 VARCHAR NOT NULL,
    trade_manifest_sha256 VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS book_snapshots (
    symbol VARCHAR NOT NULL,
    ts_exchange_ms BIGINT NOT NULL,
    ts_utc TIMESTAMPTZ NOT NULL,
    best_bid DOUBLE NOT NULL,
    best_ask DOUBLE NOT NULL,
    n_bids INTEGER NOT NULL,
    n_asks INTEGER NOT NULL,
    bids STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[] NOT NULL,
    asks STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[] NOT NULL,
    bid_depth_5 DOUBLE NOT NULL,
    ask_depth_5 DOUBLE NOT NULL,
    bid_depth_10 DOUBLE NOT NULL,
    ask_depth_10 DOUBLE NOT NULL,
    imbalance_5 DOUBLE NOT NULL,
    imbalance_10 DOUBLE NOT NULL,
    mid_price DOUBLE NOT NULL,
    micro_price DOUBLE NOT NULL,
    spread_bps DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    vendor_request_id VARCHAR NOT NULL,
    bundle_id VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS public_trades (
    symbol VARCHAR NOT NULL,
    trade_id BIGINT NOT NULL,
    ts_exchange_ms BIGINT NOT NULL,
    ts_utc TIMESTAMPTZ NOT NULL,
    aggressor_side VARCHAR NOT NULL,
    price DOUBLE NOT NULL,
    size DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    vendor_request_id VARCHAR NOT NULL,
    bundle_id VARCHAR NOT NULL
);
CREATE OR REPLACE VIEW replay_book_snapshots AS
SELECT books.*
FROM book_snapshots AS books
INNER JOIN archive_bundles AS bundles USING (bundle_id)
QUALIFY row_number() OVER (
    PARTITION BY books.symbol, books.ts_exchange_ms
    ORDER BY bundles.start_utc DESC, books.bundle_id DESC
) = 1;
CREATE OR REPLACE VIEW replay_public_trades AS
SELECT trades.*
FROM public_trades AS trades
INNER JOIN archive_bundles AS bundles USING (bundle_id)
QUALIFY row_number() OVER (
    PARTITION BY trades.symbol, trades.trade_id
    ORDER BY bundles.start_utc DESC
) = 1;
CREATE TABLE IF NOT EXISTS shadow_ledger_events (
    event_id VARCHAR PRIMARY KEY,
    source_path VARCHAR NOT NULL,
    source_line BIGINT NOT NULL,
    feed_ts VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ,
    run_id VARCHAR,
    action VARCHAR NOT NULL,
    symbol VARCHAR,
    timeframe VARCHAR,
    execution_mode VARCHAR NOT NULL,
    submitted BOOLEAN,
    place_attempted BOOLEAN,
    payload JSON NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (execution_mode IN ('paper', 'shadow'))
);
CREATE OR REPLACE VIEW shadow_regime_observations AS
SELECT
    event_id,
    source_path,
    source_line,
    run_id,
    symbol,
    timeframe,
    observed_at,
    observed_at - INTERVAL 1 MINUTE AS bar_open_at,
    CAST(json_extract(payload, '$.open') AS DOUBLE) AS open,
    CAST(json_extract(payload, '$.high') AS DOUBLE) AS high,
    CAST(json_extract(payload, '$.low') AS DOUBLE) AS low,
    CAST(json_extract(payload, '$.mark_px') AS DOUBLE) AS close,
    CAST(json_extract(payload, '$.volume') AS DOUBLE) AS volume,
    json_extract_string(payload, '$.primary_regime') AS primary_regime,
    json_extract_string(payload, '$.state_5m') AS state_5m,
    json_extract_string(payload, '$.entry_direction') AS entry_direction
FROM shadow_ledger_events
WHERE action = 'regime_observation' AND observed_at IS NOT NULL;
CREATE OR REPLACE VIEW shadow_completed_5m_bars AS
WITH unique_minutes AS (
    SELECT * EXCLUDE (ordinal)
    FROM (
        SELECT *, row_number() OVER (
            PARTITION BY run_id, symbol, bar_open_at
            ORDER BY event_id
        ) AS ordinal
        FROM shadow_regime_observations
        WHERE timeframe = '1m'
          AND open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL
          AND close IS NOT NULL AND volume IS NOT NULL
    )
    WHERE ordinal = 1
), grouped AS (
    SELECT
        run_id,
        symbol,
        time_bucket(INTERVAL '5 minutes', bar_open_at) AS bar_open_at,
        max(observed_at) AS available_at,
        arg_min(open, bar_open_at) AS open,
        max(high) AS high,
        min(low) AS low,
        arg_max(close, bar_open_at) AS close,
        sum(volume) AS volume,
        arg_max(primary_regime, bar_open_at) AS backend_primary,
        arg_max(state_5m, bar_open_at) AS backend_state_5m,
        arg_max(entry_direction, bar_open_at) AS backend_entry_direction,
        count(*) AS source_minutes,
        min(bar_open_at) AS first_minute,
        max(bar_open_at) AS last_minute
    FROM unique_minutes
    GROUP BY run_id, symbol, time_bucket(INTERVAL '5 minutes', bar_open_at)
)
SELECT * EXCLUDE (first_minute, last_minute)
FROM grouped
WHERE source_minutes = 5
  AND last_minute - first_minute = INTERVAL 4 MINUTES;
CREATE TABLE IF NOT EXISTS hypertrader_regime_annotations (
    revision VARCHAR NOT NULL,
    classifier_role VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    timeframe VARCHAR NOT NULL,
    label_time_utc TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    primary_code VARCHAR NOT NULL,
    secondary_code VARCHAR,
    confidence DOUBLE NOT NULL,
    raw_primary_code VARCHAR NOT NULL,
    raw_secondary_code VARCHAR,
    raw_confidence DOUBLE NOT NULL,
    volume_ratio DOUBLE,
    labels_sha256 VARCHAR NOT NULL,
    metadata_sha256 VARCHAR NOT NULL,
    report_only BOOLEAN NOT NULL,
    execution_authority VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (revision, symbol, timeframe, label_time_utc),
    CHECK (classifier_role IN ('strict', 'legacy')),
    CHECK (report_only),
    CHECK (execution_authority = 'none')
);
CREATE OR REPLACE VIEW shadow_hypertrader_regime_comparison AS
SELECT
    bars.run_id,
    bars.symbol,
    bars.bar_open_at,
    bars.available_at AS bar_available_at,
    bars.backend_primary,
    bars.backend_state_5m,
    bars.backend_entry_direction,
    strict.available_at AS strict_available_at,
    legacy.available_at AS legacy_available_at,
    strict.primary_code AS strict_primary,
    strict.secondary_code AS strict_secondary,
    strict.confidence AS strict_confidence,
    legacy.primary_code AS legacy_primary,
    legacy.secondary_code AS legacy_secondary,
    legacy.confidence AS legacy_confidence,
    strict.primary_code IS DISTINCT FROM legacy.primary_code AS label_disagrees
FROM shadow_completed_5m_bars AS bars
INNER JOIN hypertrader_regime_annotations AS strict
    ON strict.symbol = bars.symbol
   AND strict.timeframe = '5m'
   AND strict.classifier_role = 'strict'
   AND strict.label_time_utc = bars.bar_open_at
   AND strict.available_at <= bars.available_at
INNER JOIN hypertrader_regime_annotations AS legacy
    ON legacy.symbol = bars.symbol
   AND legacy.timeframe = '5m'
   AND legacy.classifier_role = 'legacy'
   AND legacy.label_time_utc = bars.bar_open_at
   AND legacy.available_at <= bars.available_at;
CREATE OR REPLACE VIEW shadow_completed_trade_attribution AS
WITH extracted AS (
    SELECT
        source_path,
        source_line,
        event_id,
        run_id,
        symbol,
        observed_at,
        action,
        json_extract_string(payload, '$.side') AS side,
        json_extract_string(payload, '$.client_order_id') AS client_order_id,
        json_extract_string(payload, '$.exit_reason') AS exit_reason,
        TRY_CAST(json_extract(payload, '$.fill_qty') AS DOUBLE) AS fill_qty,
        TRY_CAST(json_extract(payload, '$.fill_px') AS DOUBLE) AS fill_px,
        TRY_CAST(json_extract(payload, '$.fee_usd') AS DOUBLE) AS fee_usd,
        TRY_CAST(
            json_extract(payload, '$.funding_payment_usd') AS DOUBLE
        ) AS funding_payment_usd,
        TRY_CAST(json_extract(payload, '$.realized_pnl') AS DOUBLE)
            AS ledger_realized_pnl,
        CASE
            WHEN action IN ('liquidation', 'backstop_liquidation') THEN
                json_extract(payload, '$.liquidation_price') IS NOT NULL
                AND json_extract(payload, '$.liquidation_trigger_mark') IS NOT NULL
                AND json_extract(
                    payload, '$.liquidation_isolated_margin_usd'
                ) IS NOT NULL
                AND json_extract(
                    payload, '$.liquidation_position_equity_usd'
                ) IS NOT NULL
                AND json_extract(
                    payload, '$.liquidation_maintenance_margin_usd'
                ) IS NOT NULL
            ELSE NULL
        END AS liquidation_evidence_complete
    FROM shadow_ledger_events
    WHERE run_id IS NOT NULL AND symbol IS NOT NULL AND observed_at IS NOT NULL
), ordered AS (
    SELECT
        *,
        1 + count(*) FILTER (
            WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
        ) OVER (
            PARTITION BY source_path, run_id, symbol
            ORDER BY source_line, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS lifecycle_number
    FROM extracted
), aggregated AS (
    SELECT
        source_path,
        run_id,
        symbol,
        lifecycle_number,
        min(source_line) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS first_entry_line,
        min(observed_at) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_at,
        max(observed_at) FILTER (
            WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
        ) AS exit_at,
        arg_min(action, source_line) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_action,
        arg_min(client_order_id, source_line) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_client_order_id,
        arg_max(action, source_line) FILTER (
            WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
        ) AS terminal_action,
        arg_max(exit_reason, source_line) FILTER (
            WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
        ) AS exit_reason,
        arg_max(ledger_realized_pnl, source_line) FILTER (
            WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
        ) AS terminal_ledger_realized_pnl,
        arg_max(liquidation_evidence_complete, source_line) FILTER (
            WHERE action IN ('liquidation', 'backstop_liquidation')
        ) AS terminal_liquidation_evidence_complete,
        count(*) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_fill_count,
        count(*) FILTER (
            WHERE action IN (
                'reduce_target', 'close', 'partial_liquidation',
                'liquidation', 'backstop_liquidation'
            )
        ) AS exit_fill_count,
        sum(coalesce(fill_qty, 0.0)) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_quantity,
        sum(coalesce(fill_qty, 0.0) * coalesce(fill_px, 0.0)) FILTER (
            WHERE action IN ('enter_long', 'enter_short')
        ) AS entry_notional,
        sum(coalesce(fill_qty, 0.0)) FILTER (
            WHERE action IN (
                'reduce_target', 'close', 'partial_liquidation',
                'liquidation', 'backstop_liquidation'
            )
        ) AS exit_quantity,
        sum(coalesce(fill_qty, 0.0) * coalesce(fill_px, 0.0)) FILTER (
            WHERE action IN (
                'reduce_target', 'close', 'partial_liquidation',
                'liquidation', 'backstop_liquidation'
            )
        ) AS exit_notional,
        sum(coalesce(fee_usd, 0.0)) AS fees_usd,
        sum(coalesce(funding_payment_usd, 0.0)) AS funding_payment_usd
    FROM ordered
    GROUP BY source_path, run_id, symbol, lifecycle_number
    HAVING count(*) FILTER (
        WHERE action IN ('enter_long', 'enter_short')
    ) > 0 AND count(*) FILTER (
        WHERE action IN ('close', 'liquidation', 'backstop_liquidation')
    ) > 0
), priced AS (
    SELECT
        *,
        CASE WHEN entry_action = 'enter_long' THEN 'long' ELSE 'short' END
            AS direction,
        entry_notional / nullif(entry_quantity, 0.0) AS entry_price,
        exit_notional / nullif(exit_quantity, 0.0) AS exit_price,
        CASE
            WHEN entry_action = 'enter_long' THEN exit_notional - entry_notional
            ELSE entry_notional - exit_notional
        END AS gross_pnl_usd,
        CASE
            WHEN terminal_action NOT IN (
                'liquidation', 'backstop_liquidation'
            ) THEN 'not_applicable'
            WHEN terminal_liquidation_evidence_complete THEN 'verified'
            ELSE 'unverified_legacy'
        END AS liquidation_evidence_status
    FROM aggregated
), contextual AS (
    SELECT
        priced.*,
        intent.intent_at,
        intent.intent_at IS NOT NULL AS intent_linked,
        coalesce(intent.intent_at, priced.entry_at) AS attribution_at,
        backend.primary_regime AS backend_primary_at_entry,
        backend.state_5m AS backend_state_5m_at_entry,
        backend.entry_direction AS backend_entry_direction_at_entry,
        strict.revision AS strict_revision,
        strict.primary_code AS strict_primary_at_entry,
        strict.secondary_code AS strict_secondary_at_entry,
        legacy.revision AS legacy_revision,
        legacy.primary_code AS legacy_primary_at_entry,
        legacy.secondary_code AS legacy_secondary_at_entry
    FROM priced
    LEFT JOIN LATERAL (
        SELECT observed_at AS intent_at
        FROM extracted
        WHERE source_path = priced.source_path
          AND run_id = priced.run_id
          AND symbol = priced.symbol
          AND action = 'submit_entry'
          AND client_order_id = priced.entry_client_order_id
          AND source_line <= priced.first_entry_line
        ORDER BY source_line DESC
        LIMIT 1
    ) AS intent ON true
    LEFT JOIN LATERAL (
        SELECT primary_regime, state_5m, entry_direction
        FROM shadow_regime_observations
        WHERE source_path = priced.source_path
          AND run_id = priced.run_id
          AND symbol = priced.symbol
          AND observed_at <= coalesce(intent.intent_at, priced.entry_at)
        ORDER BY observed_at DESC, source_line DESC
        LIMIT 1
    ) AS backend ON true
    LEFT JOIN LATERAL (
        SELECT revision, primary_code, secondary_code
        FROM hypertrader_regime_annotations
        WHERE symbol = priced.symbol
          AND timeframe = '5m'
          AND classifier_role = 'strict'
          AND available_at <= coalesce(intent.intent_at, priced.entry_at)
        ORDER BY available_at DESC, label_time_utc DESC, ingested_at DESC
        LIMIT 1
    ) AS strict ON true
    LEFT JOIN LATERAL (
        SELECT revision, primary_code, secondary_code
        FROM hypertrader_regime_annotations
        WHERE symbol = priced.symbol
          AND timeframe = '5m'
          AND classifier_role = 'legacy'
          AND available_at <= coalesce(intent.intent_at, priced.entry_at)
        ORDER BY available_at DESC, label_time_utc DESC, ingested_at DESC
        LIMIT 1
    ) AS legacy ON true
)
SELECT
    * EXCLUDE (entry_action, entry_notional, exit_notional),
    exit_quantity - entry_quantity AS quantity_difference,
    abs(exit_quantity - entry_quantity) <= 0.000000000001
        AS quantity_reconciled,
    gross_pnl_usd - fees_usd - funding_payment_usd AS net_pnl_usd,
    strict_primary_at_entry IS NOT NULL
        AND backend_primary_at_entry IS NOT NULL
        AND strict_primary_at_entry IS DISTINCT FROM backend_primary_at_entry
        AS backend_strict_disagrees,
    legacy_primary_at_entry IS NOT NULL
        AND backend_primary_at_entry IS NOT NULL
        AND legacy_primary_at_entry IS DISTINCT FROM backend_primary_at_entry
        AS backend_legacy_disagrees
FROM contextual;
"""

BOOK_INSERT_SQL = """
INSERT INTO book_snapshots
WITH normalized AS (
    SELECT
        raw.symbol,
        CAST(raw.ts_exchange_ms AS BIGINT) AS ts_exchange_ms,
        CAST(raw.best_bid AS DOUBLE) AS best_bid,
        CAST(raw.best_ask AS DOUBLE) AS best_ask,
        CAST(raw.n_bids AS INTEGER) AS n_bids,
        CAST(raw.n_asks AS INTEGER) AS n_asks,
        list_transform(
            raw.bids,
            level -> struct_pack(
                n := CAST(level.n AS INTEGER),
                px := CAST(level.px AS DOUBLE),
                sz := CAST(level.sz AS DOUBLE)
            )
        ) AS bids,
        list_transform(
            raw.asks,
            level -> struct_pack(
                n := CAST(level.n AS INTEGER),
                px := CAST(level.px AS DOUBLE),
                sz := CAST(level.sz AS DOUBLE)
            )
        ) AS asks,
        raw.source,
        raw.vendor_request_id,
        files.bundle_id
    FROM read_json_auto(?, format = 'newline_delimited', filename = true) AS raw
    INNER JOIN ingest_book_files AS files ON raw.filename = files.path
), depth AS (
    SELECT
        *,
        list_sum(list_transform(list_slice(bids, 1, 5), level -> level.sz)) AS bd5,
        list_sum(list_transform(list_slice(asks, 1, 5), level -> level.sz)) AS ad5,
        list_sum(list_transform(list_slice(bids, 1, 10), level -> level.sz)) AS bd10,
        list_sum(list_transform(list_slice(asks, 1, 10), level -> level.sz)) AS ad10
    FROM normalized
)
SELECT
    symbol,
    ts_exchange_ms,
    to_timestamp(CAST(ts_exchange_ms AS DOUBLE) / 1000.0),
    best_bid,
    best_ask,
    n_bids,
    n_asks,
    bids,
    asks,
    bd5,
    ad5,
    bd10,
    ad10,
    CASE WHEN bd5 + ad5 = 0 THEN 0 ELSE (bd5 - ad5) / (bd5 + ad5) END,
    CASE WHEN bd10 + ad10 = 0 THEN 0 ELSE (bd10 - ad10) / (bd10 + ad10) END,
    (best_bid + best_ask) / 2.0,
    CASE
        WHEN bids[1].sz + asks[1].sz = 0 THEN (best_bid + best_ask) / 2.0
        ELSE ((best_ask * bids[1].sz) + (best_bid * asks[1].sz))
             / (bids[1].sz + asks[1].sz)
    END,
    10000.0 * (best_ask - best_bid) / ((best_bid + best_ask) / 2.0),
    source,
    vendor_request_id,
    bundle_id
FROM depth
"""

TRADE_INSERT_SQL = """
INSERT INTO public_trades
SELECT
    raw.symbol,
    CAST(raw.trade_id AS BIGINT),
    CAST(raw.ts_exchange_ms AS BIGINT),
    to_timestamp(CAST(raw.ts_exchange_ms AS DOUBLE) / 1000.0),
    raw.aggressor_side,
    CAST(raw.price AS DOUBLE),
    CAST(raw.size AS DOUBLE),
    raw.source,
    raw.vendor_request_id,
    files.bundle_id
FROM read_json_auto(?, format = 'newline_delimited', filename = true) AS raw
INNER JOIN ingest_trade_files AS files ON raw.filename = files.path
"""
