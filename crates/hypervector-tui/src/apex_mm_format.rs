//! Compact display formatting for the read-only Apex MM views.

use serde_json::Value;

use crate::{app::App, backend_telemetry::BackendConnectionState};

pub(crate) fn connection_label(state: BackendConnectionState) -> &'static str {
    match state {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    }
}

pub(crate) fn active_entry(app: &App) -> Option<f64> {
    app.active_position
        .is_active()
        .then_some(app.active_position.entry_price)
}

pub(crate) fn position_margin(app: &App) -> Option<f64> {
    if !app.active_position.is_active() || app.active_position.leverage <= 0.0 {
        return None;
    }
    Some(
        app.active_position.size_btc.abs() * app.active_position.entry_price
            / app.active_position.leverage,
    )
}

pub(crate) fn json_number(value: &Value, key: &str) -> Option<f64> {
    value.get(key).and_then(Value::as_f64)
}

pub(crate) fn quote_status(active: Option<bool>) -> &'static str {
    match active {
        Some(true) => "ACTIVE",
        Some(false) => "WITHHELD",
        None => "UNREPORTED",
    }
}

pub(crate) fn owned_quote(oid_value: Option<u64>, price: Option<f64>, size: Option<f64>) -> String {
    format!("#{} {} x {}", oid(oid_value), money(price), quantity(size))
}

pub(crate) fn oid(value: Option<u64>) -> String {
    value.map_or_else(|| "-".into(), |number| number.to_string())
}

pub(crate) fn money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.2}"))
}

pub(crate) fn quantity(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.6}"))
}

pub(crate) fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2} bps"))
}

pub(crate) fn percent(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}%"))
}

pub(crate) fn percent_fraction(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{:.1}%", number * 100.0))
}

pub(crate) fn millis(value: Option<u64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number}ms"))
}

pub(crate) fn horizon_label(value: Option<u64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |number| {
            if number % 1_000 == 0 {
                format!("{}s", number / 1_000)
            } else {
                format!("{number}ms")
            }
        },
    )
}

pub(crate) fn compact_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}bps"))
}
