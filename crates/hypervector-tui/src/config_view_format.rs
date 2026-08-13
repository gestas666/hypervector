//! Shared formatting primitives for effective backend configuration rows.

use serde_json::Value;

use crate::backend_telemetry::BackendTelemetrySnapshot;

/// One human-readable effective backend setting.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigMenuRow {
    pub category: String,
    pub option: String,
    pub value: String,
    pub source: String,
}

pub(crate) fn row(category: &str, option: &str, value: String, source: &str) -> ConfigMenuRow {
    ConfigMenuRow {
        category: category.into(),
        option: option.into(),
        value,
        source: source.into(),
    }
}

pub(crate) fn json_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
) -> ConfigMenuRow {
    row(category, option_name, json_value(object.get(key)), source)
}

pub(crate) fn number_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
    suffix: &str,
    multiplier: f64,
) -> ConfigMenuRow {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .map(|number| format!("{:.1}{suffix}", number * multiplier))
        .unwrap_or_else(|| "not reported".into());
    row(category, option_name, value, source)
}

pub(super) fn precise_number_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
    suffix: &str,
    multiplier: f64,
) -> ConfigMenuRow {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .map(|number| format!("{:.2}{suffix}", number * multiplier))
        .unwrap_or_else(|| "not reported".into());
    row(category, option_name, value, source)
}

pub(super) fn money_row(
    category: &str,
    option_name: &str,
    object: &Value,
    key: &str,
    source: &str,
) -> ConfigMenuRow {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .map(|number| format!("${number:.2}"))
        .unwrap_or_else(|| "not reported".into());
    row(category, option_name, value, source)
}

pub(crate) fn json_value(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Number(number)) => number.to_string(),
        Some(Value::Bool(flag)) => flag.to_string(),
        Some(Value::Array(values)) => values
            .iter()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>()
            .join(", "),
        _ => "not reported".into(),
    }
}

pub(super) fn option(value: &Option<String>) -> String {
    value.clone().unwrap_or_else(|| "not reported".into())
}

pub(super) fn effective_arm_state(backend: &BackendTelemetrySnapshot) -> String {
    match backend.execution_mode.as_deref() {
        Some("live") if backend.live_enabled == Some(true) && backend.live_armed == Some(true) => {
            "LIVE ARMED".into()
        }
        Some("shadow" | "paper") => "SHADOW".into(),
        Some("live") => "DISARMED".into(),
        Some(_) => "DISARMED".into(),
        None => "UNREPORTED".into(),
    }
}

pub(super) fn masked_credential(configured: Option<bool>) -> String {
    match configured {
        Some(true) => "******** CONFIGURED".into(),
        Some(false) => "MISSING".into(),
        None => "UNREPORTED".into(),
    }
}

pub(super) fn metalabel_inference_state(policy: &Value) -> String {
    match policy.get("inference_active").and_then(Value::as_bool) {
        Some(true) => "active".into(),
        Some(false) => "inactive".into(),
        None => "not reported".into(),
    }
}

pub(super) fn active_data_root(backend: &BackendTelemetrySnapshot) -> String {
    backend
        .data_root
        .clone()
        .unwrap_or_else(|| "not reported".into())
}

pub(super) fn shadow_reset_command(backend: &BackendTelemetrySnapshot) -> String {
    let root = active_data_root(backend);
    if root == "not reported" {
        return "active data root not reported".into();
    }
    format!(
        "uv run python -m hypervector --data-root {} hypervelocity-shadow-reset --yes",
        shell_quote(&root)
    )
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}
