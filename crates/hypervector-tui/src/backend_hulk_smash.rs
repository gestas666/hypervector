//! Read-only Hulk Smash signal and execution-plan projection.

use serde_json::Value;

use crate::backend_telemetry::LedgerRow;

/// One completed-bar Hulk decision retained for display and audit.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct BackendHulkEvent {
    pub timestamp: String,
    pub score: Option<u64>,
    pub action: String,
    pub reason: String,
}

/// Latest strategy-attributed Hulk facts from the backend ledger.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct BackendHulkTelemetry {
    pub score: Option<u64>,
    pub minimum_score: Option<u64>,
    pub candidate: Option<String>,
    pub trigger: Option<String>,
    pub evidence: Vec<String>,
    pub stop_anchor: Option<f64>,
    pub planned_stop_price: Option<f64>,
    pub planned_stop_bps: Option<f64>,
    pub planned_target_price: Option<f64>,
    pub planned_target_r_multiple: Option<f64>,
    pub latest_ack_latency_ms: Option<u64>,
    pub latest_slippage_bps: Option<f64>,
    pub latest_markout_bps: Option<f64>,
    pub latest_markout_horizon_ms: Option<u64>,
    pub latest_markout_target_ms: Option<u64>,
    pub latest_markout_lateness_ms: Option<u64>,
    pub latest_markout_recovered_after_restart: Option<bool>,
    pub liquidation_distance_pct: Option<f64>,
    pub latest_liquidity_side: Option<String>,
    pub recent_decisions: Vec<BackendHulkEvent>,
}

pub(crate) fn project_hulk_smash(rows: &[&LedgerRow]) -> BackendHulkTelemetry {
    let decision = rows.iter().rev().find(|row| is_decision(row)).copied();
    let plan = latest_action(rows, "protective_stop_plan");
    let acknowledgement = latest_acknowledgement(rows);
    let quality = latest_action(rows, "execution_quality");
    let markout = latest_action(rows, "fill_markout");
    let liquidation = latest_action(rows, "liquidation_distance");
    BackendHulkTelemetry {
        score: integer(decision, "hulk_score"),
        minimum_score: integer(decision, "hulk_minimum_score"),
        candidate: text(decision, "hulk_candidate"),
        trigger: text(decision, "hulk_trigger"),
        evidence: string_array(decision, "hulk_evidence"),
        stop_anchor: number(decision, "hulk_stop_anchor"),
        planned_stop_price: number(plan, "trigger_price"),
        planned_stop_bps: number(plan, "stop_bps"),
        planned_target_price: number(plan, "target_price"),
        planned_target_r_multiple: number(plan, "target_r_multiple"),
        latest_ack_latency_ms: integer(acknowledgement, "round_trip_latency_ms"),
        latest_slippage_bps: number(quality, "slippage_bps"),
        latest_markout_bps: number(markout, "markout_bps"),
        latest_markout_horizon_ms: integer(markout, "horizon_ms"),
        latest_markout_target_ms: integer(markout, "target_horizon_ms"),
        latest_markout_lateness_ms: integer(markout, "horizon_lateness_ms"),
        latest_markout_recovered_after_restart: boolean(markout, "recovered_after_restart"),
        liquidation_distance_pct: number(liquidation, "distance_pct"),
        latest_liquidity_side: text(quality.or(markout), "liquidity_side"),
        recent_decisions: recent_decisions(rows),
    }
}

fn latest_acknowledgement<'a>(rows: &'a [&LedgerRow]) -> Option<&'a LedgerRow> {
    rows.iter()
        .rev()
        .find(|row| {
            matches!(
                row.action.as_str(),
                "order_acknowledgement" | "stop_order" | "target_order" | "close"
            ) && row.extra.contains_key("round_trip_latency_ms")
        })
        .copied()
}

fn recent_decisions(rows: &[&LedgerRow]) -> Vec<BackendHulkEvent> {
    const MAX_DECISIONS: usize = 12;
    let mut events: Vec<BackendHulkEvent> = rows
        .iter()
        .filter(|row| is_decision(row))
        .map(|row| BackendHulkEvent {
            timestamp: row.feed_ts.clone(),
            score: integer(Some(row), "hulk_score"),
            action: text(Some(row), "decision_action").unwrap_or_else(|| row.action.clone()),
            reason: text(Some(row), "regime_reason").unwrap_or_else(|| "not reported".into()),
        })
        .collect();
    let start = events.len().saturating_sub(MAX_DECISIONS);
    events.drain(..start);
    events
}

fn is_decision(row: &LedgerRow) -> bool {
    matches!(event_type(row), "regime_decision" | "regime_history")
        && row.extra.contains_key("hulk_score")
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

fn string_array(row: Option<&LedgerRow>, key: &str) -> Vec<String> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}
