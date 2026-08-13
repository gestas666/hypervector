//! Normalize the event-sourced live ledger into the read-only TUI row schema.

use serde_json::{Map, Value};

/// Project one nested live-ledger event without changing legacy flat rows.
pub(crate) fn normalize_live_event(value: Value) -> Value {
    let Value::Object(mut row) = value else {
        return value;
    };
    let Some(event_type) = row
        .get("event_type")
        .and_then(Value::as_str)
        .map(str::to_string)
    else {
        return Value::Object(row);
    };
    let payload = row
        .get("payload")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    merge_payload(&mut row, &payload);
    preserve_operator_action(&mut row, &payload, &event_type);
    project_identity(&mut row);
    project_event(&mut row, &event_type);
    Value::Object(row)
}

fn preserve_operator_action(
    row: &mut Map<String, Value>,
    payload: &Map<String, Value>,
    event_type: &str,
) {
    if event_type == "operator_command"
        && let Some(action) = payload.get("action")
    {
        row.insert("operator_action".into(), action.clone());
    }
}

fn merge_payload(row: &mut Map<String, Value>, payload: &Map<String, Value>) {
    for (key, value) in payload {
        row.entry(key.clone()).or_insert_with(|| value.clone());
    }
    if let Some(observed) = row.get("observed_at_utc").cloned() {
        row.entry("feed_ts".to_string()).or_insert(observed);
    }
}

fn project_identity(row: &mut Map<String, Value>) {
    if row.get("execution_mode").and_then(Value::as_str) == Some("live") {
        row.insert("live_enabled".to_string(), Value::Bool(true));
    }
    if let Some(strategy) = row.get("strategy_id").cloned() {
        row.entry("strategy_name".to_string()).or_insert(strategy);
    }
}

fn project_event(row: &mut Map<String, Value>, event_type: &str) {
    let action = match event_type {
        "regime_decision" => "regime_observation",
        "fill" => fill_action(row),
        other => other,
    };
    row.insert("action".to_string(), Value::String(action.to_string()));
    match event_type {
        "fee" => project_fee(row),
        "fill" => project_fill(row),
        "funding" => rename(row, "usdc_delta", "funding_payment_usd"),
        "liquidation_price" => rename(row, "value", "liquidation_price"),
        "position" => project_position(row),
        "reconciliation" => rename(row, "account_value_usd", "equity"),
        "regime_decision" | "regime_history" => project_decision(row),
        _ => {}
    }
}

fn fill_action(row: &Map<String, Value>) -> &'static str {
    let direction = row
        .get("direction")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if direction.contains("open long") {
        "enter_long"
    } else if direction.contains("open short") {
        "enter_short"
    } else if direction.contains("close") {
        "close"
    } else {
        "fill"
    }
}

fn project_fee(row: &mut Map<String, Value>) {
    let maker = row.get("maker_rate").cloned();
    let taker = row.get("taker_rate").cloned();
    let funding = row.get("funding_source").cloned();
    if maker.is_none() && taker.is_none() {
        return;
    }
    let mut costs = Map::new();
    costs.insert("maker_fee_rate".to_string(), maker.unwrap_or(Value::Null));
    costs.insert("taker_fee_rate".to_string(), taker.unwrap_or(Value::Null));
    if let Some(source) = funding {
        costs.insert("funding_source".to_string(), source);
    }
    row.insert("costs".to_string(), Value::Object(costs));
}

fn project_fill(row: &mut Map<String, Value>) {
    rename(row, "price", "fill_px");
    rename(row, "size", "fill_qty");
    rename(row, "closed_pnl_usd", "realized_pnl");
}

fn project_position(row: &mut Map<String, Value>) {
    rename(row, "size_signed", "position_qty");
    rename(row, "entry_price", "position_avg_px");
    rename(row, "unrealized_pnl_usd", "unrealized_pnl");
}

fn project_decision(row: &mut Map<String, Value>) {
    rename(row, "reference_price", "mark_px");
    let entry_allowed = row.get("long_entry").and_then(Value::as_bool) == Some(true)
        || row.get("short_entry").and_then(Value::as_bool) == Some(true);
    row.entry("entry_allowed".to_string())
        .or_insert(Value::Bool(entry_allowed));
}

fn rename(row: &mut Map<String, Value>, source: &str, target: &str) {
    if let Some(value) = row.get(source).cloned() {
        row.entry(target.to_string()).or_insert(value);
    }
}
