//! Read-only Apex MM quote, inventory, and markout projection.

use std::collections::HashSet;

use serde_json::Value;

use crate::backend_telemetry::LedgerRow;

/// One safe, strategy-attributed event suitable for the read-only TUI.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct BackendApexMMEvent {
    pub timestamp: String,
    pub kind: String,
    pub detail: String,
}

/// Latest strategy-attributed market-maker facts from the backend ledger.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct BackendApexMMTelemetry {
    pub quote_active: Option<bool>,
    pub quote_reason: Option<String>,
    pub bid_price: Option<f64>,
    pub ask_price: Option<f64>,
    pub bid_size: Option<f64>,
    pub ask_size: Option<f64>,
    pub fair_value: Option<f64>,
    pub full_spread_bps: Option<f64>,
    pub inventory_utilization: Option<f64>,
    pub inventory_notional_usd: Option<f64>,
    pub bid_oid: Option<u64>,
    pub ask_oid: Option<u64>,
    pub position_size_signed: Option<f64>,
    pub quote_started_at_ms: Option<u64>,
    pub latest_markout_bps: Option<f64>,
    pub latest_markout_oid: Option<u64>,
    pub markout_horizon_ms: Option<u64>,
    pub latest_slippage_bps: Option<f64>,
    pub liquidation_distance_pct: Option<f64>,
    pub latest_ack_latency_ms: Option<u64>,
    pub quote_observations: usize,
    pub order_intents: usize,
    pub acknowledgement_count: usize,
    pub accepted_count: usize,
    pub rejected_count: usize,
    pub fill_count: usize,
    pub maker_fill_count: usize,
    pub taker_fill_count: usize,
    pub fault_count: usize,
    pub total_fee_usd: f64,
    pub total_funding_usd: f64,
    pub recent_events: Vec<BackendApexMMEvent>,
}

pub(crate) fn project_apex_mm(rows: &[&LedgerRow]) -> BackendApexMMTelemetry {
    let quote = latest_action(rows, "theoretical_quote");
    let state = latest_action(rows, "state_transition");
    let markout = latest_action(rows, "fill_markout");
    let execution = latest_action(rows, "execution_quality");
    let liquidation = latest_action(rows, "liquidation_distance");
    let acknowledgement = latest_action(rows, "order_acknowledgement");
    BackendApexMMTelemetry {
        quote_active: boolean(quote, "active"),
        quote_reason: text(quote, "reason"),
        bid_price: number(quote, "bid_price"),
        ask_price: number(quote, "ask_price"),
        bid_size: number(quote, "bid_size"),
        ask_size: number(quote, "ask_size"),
        fair_value: number(quote, "fair_value"),
        full_spread_bps: number(quote, "full_spread_bps"),
        inventory_utilization: number(quote, "inventory_utilization"),
        inventory_notional_usd: number(quote, "inventory_notional_usd"),
        bid_oid: reconciled_quote_oid(rows, "bid_oid"),
        ask_oid: reconciled_quote_oid(rows, "ask_oid"),
        position_size_signed: number(state, "position_size_signed"),
        quote_started_at_ms: integer(state, "quote_started_at_ms"),
        latest_markout_bps: number(markout, "markout_bps"),
        latest_markout_oid: integer(markout, "oid"),
        markout_horizon_ms: integer(markout, "horizon_ms"),
        latest_slippage_bps: number(execution, "slippage_bps"),
        liquidation_distance_pct: number(liquidation, "distance_pct"),
        latest_ack_latency_ms: integer(acknowledgement, "round_trip_latency_ms"),
        quote_observations: count(rows, "theoretical_quote"),
        order_intents: count(rows, "order_intent"),
        acknowledgement_count: count(rows, "order_acknowledgement"),
        accepted_count: count_acknowledgements(rows, true),
        rejected_count: count_acknowledgements(rows, false),
        fill_count: count(rows, "fill"),
        maker_fill_count: count_fills(rows, false),
        taker_fill_count: count_fills(rows, true),
        fault_count: count(rows, "fault"),
        total_fee_usd: total_fees(rows),
        total_funding_usd: rows
            .iter()
            .filter(|row| event_type(row) == "funding")
            .filter_map(|row| row.funding_payment_usd)
            .sum(),
        recent_events: recent_events(rows),
    }
}

fn reconciled_quote_oid(rows: &[&LedgerRow], key: &str) -> Option<u64> {
    let state_index = rows
        .iter()
        .rposition(|row| row.action == "state_transition")?;
    let oid = integer(Some(rows[state_index]), key)?;
    let reconciliation_index = rows.iter().rposition(|row| row.action == "reconciliation");
    let Some(index) = reconciliation_index.filter(|index| *index > state_index) else {
        return Some(oid);
    };
    let open_orders = rows[index]
        .extra
        .get("open_order_ids")
        .and_then(Value::as_array)?;
    open_orders
        .iter()
        .filter_map(Value::as_u64)
        .any(|open_oid| open_oid == oid)
        .then_some(oid)
}

fn count(rows: &[&LedgerRow], expected: &str) -> usize {
    rows.iter()
        .filter(|row| event_type(row) == expected)
        .count()
}

fn count_acknowledgements(rows: &[&LedgerRow], accepted: bool) -> usize {
    rows.iter()
        .filter(|row| event_type(row) == "order_acknowledgement")
        .filter(|row| boolean(Some(row), "accepted") == Some(accepted))
        .count()
}

fn count_fills(rows: &[&LedgerRow], crossed: bool) -> usize {
    rows.iter()
        .filter(|row| event_type(row) == "fill")
        .filter(|row| boolean(Some(row), "crossed") == Some(crossed))
        .count()
}

fn total_fees(rows: &[&LedgerRow]) -> f64 {
    let reported_fee_rows: Vec<&&LedgerRow> = rows
        .iter()
        .filter(|row| {
            event_type(row) == "fee" && text(Some(row), "source").as_deref() == Some("fill")
        })
        .collect();
    if reported_fee_rows.is_empty() {
        return rows
            .iter()
            .filter(|row| event_type(row) == "fill")
            .filter_map(|row| row.fee_usd)
            .sum();
    }
    let reported_oids: HashSet<u64> = reported_fee_rows
        .iter()
        .filter_map(|row| integer(Some(row), "oid"))
        .collect();
    let reported: f64 = reported_fee_rows.iter().filter_map(|row| row.fee_usd).sum();
    let unpaired: f64 = rows
        .iter()
        .filter(|row| event_type(row) == "fill")
        .filter(|row| integer(Some(row), "oid").is_some_and(|oid| !reported_oids.contains(&oid)))
        .filter_map(|row| row.fee_usd)
        .sum();
    reported + unpaired
}

fn recent_events(rows: &[&LedgerRow]) -> Vec<BackendApexMMEvent> {
    const MAX_EVENTS: usize = 16;
    let mut events: Vec<BackendApexMMEvent> =
        rows.iter().filter_map(|row| display_event(row)).collect();
    let start = events.len().saturating_sub(MAX_EVENTS);
    events.drain(..start);
    events
}

fn display_event(row: &LedgerRow) -> Option<BackendApexMMEvent> {
    let kind = event_type(row);
    let detail = match kind {
        "theoretical_quote" => quote_detail(row),
        "state_transition" => state_detail(row),
        "order_intent" => intent_detail(row),
        "order_acknowledgement" => acknowledgement_detail(row),
        "fill" => fill_detail(row),
        "execution_quality" => signed_detail("slippage", number(Some(row), "slippage_bps"), "bps"),
        "fee" if text(Some(row), "source").as_deref() == Some("fill") => {
            format!(
                "OID {} fee ${:.4}",
                oid_label(row),
                row.fee_usd.unwrap_or(0.0)
            )
        }
        "funding" => format!(
            "venue payment {:+.4} USD",
            row.funding_payment_usd.unwrap_or(0.0)
        ),
        "liquidation_distance" => signed_detail("distance", number(Some(row), "distance_pct"), "%"),
        "fill_markout" => signed_detail("markout", number(Some(row), "markout_bps"), "bps"),
        "fault" => {
            text(Some(row), "message").unwrap_or_else(|| "backend fault without message".into())
        }
        _ => return None,
    };
    Some(BackendApexMMEvent {
        timestamp: row.feed_ts.clone(),
        kind: kind.replace('_', " ").to_uppercase(),
        detail,
    })
}

fn quote_detail(row: &LedgerRow) -> String {
    let status = if boolean(Some(row), "active") == Some(true) {
        "ACTIVE"
    } else {
        "WITHHELD"
    };
    format!(
        "{status} bid {} / ask {} ({})",
        price_label(number(Some(row), "bid_price")),
        price_label(number(Some(row), "ask_price")),
        text(Some(row), "reason").unwrap_or_else(|| "reason not reported".into())
    )
}

fn state_detail(row: &LedgerRow) -> String {
    format!(
        "{} bid #{} / ask #{}",
        text(Some(row), "state").unwrap_or_else(|| "UNKNOWN".into()),
        integer(Some(row), "bid_oid").map_or_else(|| "-".into(), |value| value.to_string()),
        integer(Some(row), "ask_oid").map_or_else(|| "-".into(), |value| value.to_string())
    )
}

fn intent_detail(row: &LedgerRow) -> String {
    format!(
        "{} {} at {}",
        text(Some(row), "operation").unwrap_or_else(|| "operation".into()),
        text(Some(row), "side").unwrap_or_else(|| "side not reported".into()),
        price_label(number(Some(row), "limit_price"))
    )
}

fn acknowledgement_detail(row: &LedgerRow) -> String {
    let accepted = if boolean(Some(row), "accepted") == Some(true) {
        "ACCEPTED"
    } else {
        "REJECTED"
    };
    format!(
        "{accepted} OID {} {}ms",
        oid_label(row),
        integer(Some(row), "round_trip_latency_ms").unwrap_or(0)
    )
}

fn fill_detail(row: &LedgerRow) -> String {
    let liquidity = match boolean(Some(row), "crossed") {
        Some(false) => "MAKER",
        Some(true) => "TAKER",
        None => "UNKNOWN",
    };
    format!(
        "{liquidity} {} {} @ {} fee ${:.4}",
        text(Some(row), "side").unwrap_or_else(|| "?".into()),
        number(Some(row), "size").unwrap_or(0.0),
        price_label(number(Some(row), "price")),
        row.fee_usd.unwrap_or(0.0)
    )
}

fn signed_detail(label: &str, value: Option<f64>, unit: &str) -> String {
    value.map_or_else(
        || format!("{label} not reported"),
        |number| format!("{label} {number:+.2}{unit}"),
    )
}

fn oid_label(row: &LedgerRow) -> String {
    integer(Some(row), "oid").map_or_else(|| "-".into(), |value| value.to_string())
}

fn price_label(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |price| format!("${price:.2}"))
}

fn event_type(row: &LedgerRow) -> &str {
    row.extra
        .get("event_type")
        .and_then(Value::as_str)
        .unwrap_or(&row.action)
}

fn latest_action<'a>(rows: &'a [&LedgerRow], action: &str) -> Option<&'a LedgerRow> {
    rows.iter().rev().find(|row| row.action == action).copied()
}

fn number(row: Option<&LedgerRow>, key: &str) -> Option<f64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_f64)
}

fn integer(row: Option<&LedgerRow>, key: &str) -> Option<u64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_u64)
}

fn boolean(row: Option<&LedgerRow>, key: &str) -> Option<bool> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_bool)
}

fn text(row: Option<&LedgerRow>, key: &str) -> Option<String> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_str)
        .map(str::to_string)
}
