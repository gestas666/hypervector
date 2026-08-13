//! Canonical regime-policy rows for the read-only configuration screen.

use serde_json::Value;

use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::config_view::{ConfigMenuRow, json_row, json_value, number_row, row};

pub(crate) fn regime_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let policy = &backend.regime_policy;
    if is_source_follow(policy) {
        let mut rows = source_follow_timeframe_rows(policy);
        rows.extend(source_follow_rows(policy));
        rows.extend(policy_rows(policy));
        return rows;
    }
    let mut rows = timeframe_rows(policy);
    rows.extend(structure_rows(policy));
    rows.extend(tactical_rows(policy));
    rows.extend(breakout_rows(policy));
    rows.extend(policy_rows(policy));
    rows
}

fn source_follow_timeframe_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Regime",
            "Decision timeframe",
            policy,
            "execution_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Primary regime timeframe",
            policy,
            "primary_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Context timeframe",
            policy,
            "context_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "1m classification",
            policy,
            "state_1m_role",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "15m classification",
            policy,
            "context_role",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Context hard gate",
            policy,
            "context_is_hard_gate",
            "regime_policy",
        ),
    ]
}

fn is_source_follow(policy: &Value) -> bool {
    policy.get("engine").and_then(Value::as_str) == Some("pinned_hypertrader_source_follow_v1")
}

fn source_follow_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    let mut rows = source_follow_identity_rows(policy);
    rows.extend(source_follow_range_rows(policy));
    rows.extend(source_follow_trigger_rows(policy));
    rows
}

fn source_follow_identity_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        json_row("Regime", "Regime engine", policy, "engine", "regime_policy"),
        json_row(
            "Regime",
            "Source revision",
            policy,
            "source_revision",
            "regime_policy",
        ),
        json_row("Regime", "Source side", policy, "side", "regime_policy"),
        number_row(
            "Regime",
            "Minimum confidence",
            policy,
            "minimum_confidence",
            "regime_policy",
            "%",
            100.0,
        ),
    ]
}

fn source_follow_range_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![number_row(
        "Regime",
        "Minimum 5m range",
        policy,
        "minimum_completed_5m_range_bps",
        "regime_policy",
        " bps",
        1.0,
    )]
}

fn source_follow_trigger_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Regime",
            "Maximum 5m range",
            policy,
            "maximum_completed_5m_range_bps",
            "regime_policy",
            " bps",
            1.0,
        ),
        number_row(
            "Trigger",
            "Decision delay",
            policy,
            "decision_delay_seconds",
            "regime_policy",
            "s",
            1.0,
        ),
        number_row(
            "Trigger",
            "Entry pulse",
            policy,
            "entry_pulse_seconds",
            "regime_policy",
            "s",
            1.0,
        ),
        json_row("Runtime", "Session", policy, "session", "regime_policy"),
    ]
}

fn timeframe_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Regime",
            "Execution timeframe",
            policy,
            "execution_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Primary regime timeframe",
            policy,
            "primary_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Context timeframe",
            policy,
            "context_timeframe",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Context hard gate",
            policy,
            "context_is_hard_gate",
            "regime_policy",
        ),
    ]
}

fn structure_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Regime",
            "EMA pair",
            pair_value(policy, "ema_fast", "ema_slow"),
            "regime_policy",
        ),
        number_row(
            "Regime",
            "Structure lookback",
            policy,
            "structure_lookback",
            "regime_policy",
            " bars",
            1.0,
        ),
        number_row(
            "Regime",
            "Minimum EMA gap",
            policy,
            "minimum_trend_gap_bps",
            "regime_policy",
            " bps",
            1.0,
        ),
        json_row(
            "Regime",
            "Range filter",
            policy,
            "range_filter",
            "regime_policy",
        ),
    ]
}

fn tactical_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Trigger",
            "Entry trigger",
            policy,
            "entry_trigger",
            "regime_policy",
        ),
        json_row(
            "Trigger",
            "Tactical setup",
            policy,
            "tactical_setup",
            "regime_policy",
        ),
        json_row(
            "Trigger",
            "Tactical setup gate",
            policy,
            "tactical_setup_is_gate",
            "regime_policy",
        ),
        row(
            "Trigger",
            "BBWP length/lookback",
            pair_value(policy, "bbwp_length", "bbwp_lookback"),
            "regime_policy",
        ),
        row(
            "Trigger",
            "BBWP compression",
            less_than_value(policy, "bbwp_compression_threshold", "%"),
            "regime_policy",
        ),
        row(
            "Trigger",
            "RSI / signal EMA",
            pair_value(policy, "rsi_length", "rsi_signal_length"),
            "regime_policy",
        ),
    ]
}

fn breakout_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Breakout",
            "Range lookback",
            policy,
            "breakout_lookback",
            "regime_policy",
            " bars",
            1.0,
        ),
        number_row(
            "Breakout",
            "Breakout clearance",
            policy,
            "breakout_clearance_bps",
            "regime_policy",
            " bps",
            1.0,
        ),
        row(
            "Breakout",
            "Breakout volume",
            breakout_volume_value(policy),
            "regime_policy",
        ),
    ]
}

fn policy_rows(policy: &Value) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Regime",
            "Allowed entry states",
            policy,
            "allowed_entry_states",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Blocked entry states",
            policy,
            "blocked_entry_states",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Breakout direction required",
            policy,
            "breakout_requires_direction",
            "regime_policy",
        ),
        json_row(
            "Regime",
            "Strength score is gate",
            policy,
            "confidence_is_gate",
            "regime_policy",
        ),
    ]
}

fn pair_value(object: &Value, first: &str, second: &str) -> String {
    format!(
        "{} / {}",
        json_value(object.get(first)),
        json_value(object.get(second))
    )
}

fn less_than_value(object: &Value, key: &str, suffix: &str) -> String {
    object.get(key).and_then(Value::as_f64).map_or_else(
        || "not reported".into(),
        |value| format!("<{value:.1}{suffix}"),
    )
}

fn breakout_volume_value(object: &Value) -> String {
    let multiple = object
        .get("breakout_volume_multiple")
        .and_then(Value::as_f64);
    let lookback = object
        .get("breakout_volume_lookback")
        .and_then(Value::as_u64);
    match (multiple, lookback) {
        (Some(multiple), Some(lookback)) => format!("{multiple:.2}x / {lookback} bars"),
        _ => "not reported".into(),
    }
}
