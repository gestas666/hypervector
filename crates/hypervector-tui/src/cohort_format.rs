//! Formatting helpers for backend-authored multi-asset cohort telemetry.

use chrono::{DateTime, Utc};
use chrono_tz::America::New_York;
use ratatui::style::Style;

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;

pub(crate) fn connection_label(app: &App) -> &'static str {
    match app.backend.connection {
        BackendConnectionState::Connected => "BACKEND CONNECTED",
        BackendConnectionState::Stale => "BACKEND STALE",
        BackendConnectionState::Disconnected => "BACKEND DISCONNECTED",
        BackendConnectionState::Error => "BACKEND ERROR",
    }
}

pub(crate) fn connection_style(app: &App) -> Style {
    match app.backend.connection {
        BackendConnectionState::Connected => app.theme.bull,
        BackendConnectionState::Stale => app.theme.gold,
        BackendConnectionState::Disconnected | BackendConnectionState::Error => app.theme.bear,
    }
}

pub(crate) fn money(value: f64) -> String {
    format!("${value:.2}")
}

pub(crate) fn signed_money(value: f64) -> String {
    format!("{value:+.2}")
}

pub(crate) fn number(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.4}"))
}

pub(crate) fn compact_number(value: Option<f64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |number| {
            if number.abs() >= 1_000.0 {
                format!("${number:.0}")
            } else if number.abs() >= 100.0 {
                format!("${number:.2}")
            } else {
                format!("${number:.3}")
            }
        },
    )
}

pub(crate) fn percent(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}%"))
}

pub(crate) fn optional_money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), money)
}

pub(crate) fn optional_signed_money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), signed_money)
}

pub(crate) fn optional_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}bps"))
}

pub(crate) fn markout(value: Option<f64>, horizon_ms: Option<u64>) -> String {
    match (value, horizon_ms) {
        (Some(bps), Some(horizon)) => format!("{bps:+.2}bps/{}ms", horizon),
        _ => "PENDING".into(),
    }
}

pub(crate) fn fill_time(value: u64) -> String {
    eastern_timestamp(value, "%H:%M:%S %Z")
}

pub(crate) fn fill_date_time(value: u64) -> String {
    eastern_timestamp(value, "%m-%d %H:%M %Z")
}

pub(crate) fn fill_full_date_time(value: u64) -> String {
    eastern_timestamp(value, "%m-%d %H:%M:%S %Z")
}

fn eastern_timestamp(value: u64, format: &str) -> String {
    i64::try_from(value)
        .ok()
        .and_then(DateTime::<Utc>::from_timestamp_millis)
        .map(|time| time.with_timezone(&New_York).format(format).to_string())
        .unwrap_or_else(|| "INVALID".into())
}

pub(crate) fn eastern_time(value: &str) -> String {
    DateTime::parse_from_rfc3339(value)
        .map(|time| {
            time.with_timezone(&New_York)
                .format("%H:%M:%S %Z")
                .to_string()
        })
        .unwrap_or_else(|_| "INVALID".into())
}
