//! Timestamp normalization and Eastern-time display helpers.

use chrono::{DateTime, NaiveDateTime, TimeZone, Utc};
use chrono_tz::{America::New_York, Tz};

pub(super) fn normalized_timestamp(ts: &str) -> String {
    let today = crate::data_loader::get_today_date_str();
    ts.replace("1969-12-31", &today)
        .replace("1970-01-01", &today)
}

fn eastern_timestamp(ts: &str) -> Option<DateTime<Tz>> {
    DateTime::parse_from_rfc3339(ts)
        .ok()
        .map(|value| value.with_timezone(&New_York))
        .or_else(|| eastern_from_utc_label(ts))
}

fn eastern_from_utc_label(ts: &str) -> Option<DateTime<Tz>> {
    let raw = ts.strip_suffix(" UTC")?;
    let naive = NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S").ok()?;
    Some(Utc.from_utc_datetime(&naive).with_timezone(&New_York))
}

/// Format a backend timestamp as an Eastern date-time display when possible.
pub fn format_timestamp_display(ts: &str) -> String {
    let fixed_ts = normalized_timestamp(ts);
    if let Some(eastern) = eastern_timestamp(&fixed_ts) {
        return eastern.format("%Y-%m-%d %H:%M:%S %Z").to_string();
    }
    if fixed_ts.contains('T') {
        let parts: Vec<&str> = fixed_ts.split('T').collect();
        let date = parts[0];
        let time = parts
            .get(1)
            .unwrap_or(&"")
            .split('.')
            .next()
            .unwrap_or("")
            .trim_end_matches('Z');
        format!("{} {}", date, time)
    } else {
        fixed_ts
    }
}

/// Format a backend timestamp as an Eastern time display when possible.
pub fn format_time_display(ts: &str) -> String {
    let fixed_ts = normalized_timestamp(ts);
    if let Some(eastern) = eastern_timestamp(&fixed_ts) {
        return eastern.format("%H:%M:%S %Z").to_string();
    }
    let time_str = if fixed_ts.contains('T') {
        fixed_ts.split('T').nth(1).unwrap_or("")
    } else if fixed_ts.contains(' ') {
        fixed_ts.split(' ').nth(1).unwrap_or("")
    } else {
        &fixed_ts
    };
    let time_clean = time_str
        .split('.')
        .next()
        .unwrap_or(time_str)
        .trim_end_matches('Z');
    if time_clean.is_empty() {
        fixed_ts
    } else {
        time_clean.to_string()
    }
}
