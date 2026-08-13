//! Read-only effective-configuration rows for Hulk Smash.

use serde_json::Value;

use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::config_view::{ConfigMenuRow, json_row, number_row, row};

pub(crate) fn hulk_smash_strategy_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let (stop_clamp, target) = exit_labels(&backend.exits);
    vec![
        json_row(
            "Position",
            "Position mode",
            &backend.position_policy,
            "position_mode",
            "position_policy",
        ),
        json_row(
            "Position",
            "Max per symbol",
            &backend.position_policy,
            "max_positions_per_symbol",
            "position_policy",
        ),
        number_row(
            "Risk",
            "Leverage",
            &backend.strategy_params,
            "leverage",
            "strategy_params",
            "x",
            1.0,
        ),
        json_row(
            "Signal",
            "Signal score",
            &backend.strategy_params,
            "minimum_score",
            "strategy_params",
        ),
        structural_pivot_row(backend),
        row("Risk", "Stop clamp", stop_clamp, "exits"),
        row("Exit", "Profit target", target, "exits"),
        number_row(
            "Exit",
            "Maximum hold",
            &backend.exits,
            "maximum_hold_bars",
            "exits",
            " bars",
            1.0,
        ),
        maximum_entry_age_row(backend),
        markout_horizon_row(backend),
        offline_status_row(backend),
    ]
}

fn exit_labels(exits: &Value) -> (String, String) {
    let minimum = exits.get("minimum_stop_bps").and_then(Value::as_f64);
    let maximum = exits.get("maximum_stop_bps").and_then(Value::as_f64);
    let stop = match (minimum, maximum) {
        (Some(low), Some(high)) => format!("{low:.1}-{high:.1} bps"),
        _ => "not reported".into(),
    };
    let target = exits
        .get("target_r_multiple")
        .and_then(Value::as_f64)
        .map_or_else(|| "not reported".into(), |value| format!("{value:.1}R"));
    (stop, target)
}

fn structural_pivot_row(backend: &BackendTelemetrySnapshot) -> ConfigMenuRow {
    let value = backend
        .strategy_params
        .get("pivot_bars")
        .and_then(Value::as_u64)
        .map_or_else(|| "not reported".into(), |bars| format!("{bars} bars"));
    row("Signal", "Structural pivot", value, "strategy_params")
}

fn maximum_entry_age_row(backend: &BackendTelemetrySnapshot) -> ConfigMenuRow {
    let value = backend
        .execution_policy
        .get("maximum_entry_delay_seconds")
        .and_then(Value::as_u64)
        .map_or_else(
            || "not reported".into(),
            |seconds| format!("{seconds} seconds"),
        );
    row("Execution", "Maximum entry age", value, "execution")
}

fn markout_horizon_row(backend: &BackendTelemetrySnapshot) -> ConfigMenuRow {
    let value = backend
        .execution_policy
        .get("markout_horizon_ms")
        .and_then(Value::as_u64)
        .map_or_else(
            || "not reported".into(),
            |milliseconds| format!("{milliseconds} ms"),
        );
    row("Measurement", "Markout horizon", value, "execution")
}

fn offline_status_row(backend: &BackendTelemetrySnapshot) -> ConfigMenuRow {
    let value = backend
        .runtime
        .get("offline_edge_status")
        .and_then(Value::as_str)
        .unwrap_or("not reported")
        .into();
    row("Validation", "Offline status", value, "runtime")
}
