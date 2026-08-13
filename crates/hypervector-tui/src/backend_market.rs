//! Backend regime and L2 ledger projection for the read-only TUI.

use chrono::DateTime;
use serde_json::Value;

use crate::backend_telemetry::LedgerRow;
use crate::model::{BookLevel, RegimeSnapshot, RegimeState};

const MAX_MM_BOOK_DISPLAY_SNAPSHOTS: usize = 600;

/// Latest measured L2 state published by the backend.
#[derive(Debug, Clone)]
pub struct BackendBookTelemetry {
    pub source: String,
    pub exchange_ts_ms: Option<f64>,
    pub recv_ts_ms: f64,
    pub mid_price: f64,
    pub spread_bps: f64,
    pub bid_depth_ratio: f64,
    pub opi: f64,
    pub bid_levels: Vec<BookLevel>,
    pub ask_levels: Vec<BookLevel>,
}

pub(crate) fn build_regime_snapshots(
    rows: &[&LedgerRow],
    configured_leverage: f64,
) -> Vec<RegimeSnapshot> {
    let classified: Vec<RegimeSnapshot> = rows
        .iter()
        .filter(|row| matches!(row.action.as_str(), "regime_observation" | "regime_history"))
        .enumerate()
        .filter_map(|(index, row)| regime_snapshot(row, index, configured_leverage))
        .collect();
    if !classified.is_empty() || !is_apex_mm(rows) {
        return classified;
    }
    let books: Vec<&LedgerRow> = rows
        .iter()
        .filter(|row| row.action == "book_observation")
        .copied()
        .collect();
    let start = books.len().saturating_sub(MAX_MM_BOOK_DISPLAY_SNAPSHOTS);
    books[start..]
        .iter()
        .enumerate()
        .filter_map(|(index, row)| mm_book_display_snapshot(row, index))
        .collect()
}

fn is_apex_mm(rows: &[&LedgerRow]) -> bool {
    rows.iter().any(|row| {
        row.strategy_name.as_deref() == Some("apex_regime_mm_v2")
            || row.extra.get("strategy_id").and_then(Value::as_str) == Some("apex_regime_mm_v2")
            || row.extra.get("strategy_name").and_then(Value::as_str) == Some("apex_regime_mm_v2")
    })
}

fn mm_book_display_snapshot(row: &LedgerRow, index: usize) -> Option<RegimeSnapshot> {
    let midpoint = number(row, "mid_px")?;
    Some(RegimeSnapshot {
        timestamp_str: row.feed_ts.clone(),
        timestamp_ms: timestamp_ms(&row.feed_ts, index),
        price: midpoint,
        open: Some(midpoint),
        high: midpoint,
        low: midpoint,
        volume: 0.0,
        state: RegimeState::Unknown,
        regime_reason: "backend_book_display_only_not_classified".into(),
        confidence: 0.0,
        regime_score_source: "not_classified".into(),
        source_diagnostics: None,
        opi: number(row, "opi").unwrap_or(0.0),
        spread_bps: number(row, "spread_bps").unwrap_or(0.0),
        bid_depth_ratio: number(row, "bid_depth_ratio").unwrap_or(0.0),
        microstructure_source: text(row, "source").unwrap_or_else(|| "not_reported".into()),
        bbwp_percentile: 0.0,
        rsi: 0.0,
        funding_zscore: 0.0,
        funding_source: "venue_payments_only".into(),
        trend_1m: "NOT_CLASSIFIED".into(),
        trend_5m: "NOT_CLASSIFIED".into(),
        trend_15m: "NOT_CLASSIFIED".into(),
        long_weight: 0.0,
        short_weight: 0.0,
        max_leverage: 0.0,
        dynamic_leverage: 0.0,
        taker_allowed: false,
    })
}

pub(crate) fn latest_book(rows: &[&LedgerRow]) -> Option<BackendBookTelemetry> {
    let row = rows
        .iter()
        .rev()
        .find(|row| row.action == "book_observation")?;
    Some(BackendBookTelemetry {
        source: text(row, "source").unwrap_or_else(|| "unknown".into()),
        exchange_ts_ms: number(row, "exchange_ts_ms"),
        recv_ts_ms: number(row, "recv_ts_ms")?,
        mid_price: number(row, "mid_px")?,
        spread_bps: number(row, "spread_bps")?,
        bid_depth_ratio: number(row, "bid_depth_ratio")?,
        opi: number(row, "opi")?,
        bid_levels: levels(row, "bids"),
        ask_levels: levels(row, "asks"),
    })
}

fn regime_snapshot(
    row: &LedgerRow,
    index: usize,
    configured_leverage: f64,
) -> Option<RegimeSnapshot> {
    let primary = row.primary_regime.as_deref()?;
    let state = regime_state(primary);
    let price = row.mark_px.or(row.fill_px).unwrap_or(0.0);
    let eligible = boolean(row, "entry_allowed").unwrap_or(false);
    let direction = text(row, "entry_direction");
    Some(RegimeSnapshot {
        timestamp_str: row.feed_ts.clone(),
        timestamp_ms: timestamp_ms(&row.feed_ts, index),
        price,
        open: number(row, "open"),
        high: number(row, "high").unwrap_or(price),
        low: number(row, "low").unwrap_or(price),
        volume: number(row, "volume").unwrap_or(0.0),
        state,
        regime_reason: text(row, "regime_reason").unwrap_or_else(|| "not_reported".into()),
        confidence: number(row, "regime_strength_score")
            .or_else(|| number(row, "confidence"))
            .unwrap_or(0.0),
        regime_score_source: text(row, "regime_score_source")
            .unwrap_or_else(|| "legacy_confidence_alias".into()),
        source_diagnostics: row.regime_diagnostics.clone(),
        opi: 0.0,
        spread_bps: 0.0,
        bid_depth_ratio: 0.0,
        microstructure_source: "not_available".into(),
        bbwp_percentile: number(row, "bbwp_percentile").unwrap_or(0.0),
        rsi: number(row, "rsi").unwrap_or(50.0),
        funding_zscore: number(row, "funding_zscore").unwrap_or(0.0),
        funding_source: text(row, "funding_source").unwrap_or_else(|| "not_available".into()),
        trend_1m: text(row, "state_1m").unwrap_or_else(|| primary.to_string()),
        trend_5m: text(row, "state_5m").unwrap_or_else(|| primary.to_string()),
        trend_15m: text(row, "context_15m").unwrap_or_else(|| "UNKNOWN".into()),
        long_weight: weight(direction.as_deref(), "long"),
        short_weight: weight(direction.as_deref(), "short"),
        max_leverage: if eligible { configured_leverage } else { 0.0 },
        dynamic_leverage: if eligible { configured_leverage } else { 0.0 },
        taker_allowed: false,
    })
}

fn regime_state(label: &str) -> RegimeState {
    match label {
        "TREND_UP" => RegimeState::BullMomentum,
        "TREND_DOWN" => RegimeState::BearMomentum,
        "BREAKOUT" => RegimeState::VolatilityCoiling,
        "TRANSITION" => RegimeState::FundingCarry,
        "RANGE" => RegimeState::RangeChop,
        _ => RegimeState::Unknown,
    }
}

fn timestamp_ms(value: &str, index: usize) -> u64 {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .and_then(|timestamp| u64::try_from(timestamp.timestamp_millis()).ok())
        .unwrap_or(index as u64 * 60_000)
}

fn weight(direction: Option<&str>, expected: &str) -> f64 {
    if direction == Some(expected) {
        1.0
    } else {
        0.0
    }
}

fn number(row: &LedgerRow, key: &str) -> Option<f64> {
    row.extra.get(key).and_then(Value::as_f64)
}

fn text(row: &LedgerRow, key: &str) -> Option<String> {
    row.extra
        .get(key)
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn boolean(row: &LedgerRow, key: &str) -> Option<bool> {
    row.extra.get(key).and_then(Value::as_bool)
}

fn levels(row: &LedgerRow, key: &str) -> Vec<BookLevel> {
    row.extra
        .get(key)
        .cloned()
        .and_then(|value| serde_json::from_value(value).ok())
        .unwrap_or_default()
}
