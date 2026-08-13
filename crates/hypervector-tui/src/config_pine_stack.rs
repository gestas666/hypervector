//! Effective backend configuration rows for the four-Pine observer.

use serde_json::Value;

use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::config_view::ConfigMenuRow;

pub(crate) fn pine_stack_config_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let mut rows = runtime_evidence_rows(backend);
    rows.extend(signal_rows(backend));
    rows.extend(tp_rows(backend));
    rows.extend(research_rows(backend));
    rows
}

fn runtime_evidence_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Runtime",
            "Strategy",
            option(&backend.strategy_name),
            "session_start",
        ),
        row(
            "Runtime",
            "Symbol",
            option(&backend.symbol),
            "session_start",
        ),
        row(
            "Runtime",
            "Execution mode",
            option(&backend.execution_mode),
            "session_start",
        ),
        row(
            "Runtime",
            "Execution authority",
            option(&backend.execution_authority),
            "backend-confirmed",
        ),
        row(
            "Evidence",
            "Candidate status",
            option(&backend.pine_stack.candidate_status),
            "backend ledger",
        ),
        row(
            "Portfolio",
            "Capital",
            money(&backend.risk, "capital_usd"),
            "risk",
        ),
    ]
}

fn signal_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Classification",
            "Canonical regime",
            text(&backend.regime_policy, "classification"),
            "regime_policy",
        ),
        row(
            "Signal",
            "Completed timeframe",
            text(&backend.regime_policy, "signal_timeframe"),
            "regime_policy",
        ),
        row(
            "CS Supertrend",
            "ATR period",
            number(&backend.strategy_params, "cs_atr_period"),
            "strategy_params",
        ),
        row(
            "CS Supertrend",
            "Sensitivity",
            number(&backend.strategy_params, "cs_sensitivity"),
            "strategy_params",
        ),
        row(
            "Trend Levels",
            "Lookback",
            number(&backend.strategy_params, "trend_lookback"),
            "strategy_params",
        ),
        row(
            "Market Sentiment",
            "Role",
            text(&backend.strategy_params, "sentiment_role"),
            "strategy_params",
        ),
    ]
}

fn tp_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "TP Dimensions",
            "Pivot width",
            number(&backend.strategy_params, "tp_pivot_width"),
            "strategy_params",
        ),
        row(
            "TP Dimensions",
            "Bins",
            number(&backend.strategy_params, "tp_bins"),
            "strategy_params",
        ),
        row(
            "TP Dimensions",
            "Minimum pool",
            number(&backend.strategy_params, "tp_minimum_directional_pool"),
            "strategy_params",
        ),
        row(
            "TP Dimensions",
            "Time-of-day axis",
            text(&backend.strategy_params, "tp_time_of_day_axis"),
            "strategy_params",
        ),
    ]
}

fn research_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        row(
            "Research",
            "Exit control",
            text(&backend.exits, "research_control"),
            "exits",
        ),
        row(
            "Research",
            "Margin stop",
            suffix(&backend.exits, "stop_margin_pct", "%"),
            "exits",
        ),
        row(
            "Research",
            "Next-bar model",
            text(&backend.execution_policy, "next_bar_model"),
            "execution",
        ),
        row(
            "Deferred",
            "xyz:SP500 HIP-3",
            "deferred".into(),
            "user decision",
        ),
    ]
}

fn row(category: &str, option: &str, value: String, source: &str) -> ConfigMenuRow {
    ConfigMenuRow {
        category: category.into(),
        option: option.into(),
        value,
        source: source.into(),
    }
}

fn option(value: &Option<String>) -> String {
    value.clone().unwrap_or_else(|| "not reported".into())
}

fn text(value: &Value, key: &str) -> String {
    value.get(key).map_or_else(
        || "not reported".into(),
        |item| match item {
            Value::String(text) => text.clone(),
            _ => item.to_string(),
        },
    )
}

fn number(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_f64)
        .map_or_else(|| "not reported".into(), compact_number)
}

fn money(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_f64)
        .map_or_else(|| "not reported".into(), |number| format!("${number:.2}"))
}

fn suffix(value: &Value, key: &str, suffix: &str) -> String {
    value.get(key).and_then(Value::as_f64).map_or_else(
        || "not reported".into(),
        |number| format!("{}{suffix}", compact_number(number)),
    )
}

fn compact_number(number: f64) -> String {
    if number.fract().abs() < f64::EPSILON {
        format!("{number:.0}")
    } else {
        format!("{number:.3}")
    }
}
