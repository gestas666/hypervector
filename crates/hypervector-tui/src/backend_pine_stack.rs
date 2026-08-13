//! Read-only projection of the four-Pine ETH 30m forward observer.

use serde_json::Value;

use crate::backend_telemetry::LedgerRow;

/// One completed-bar decision retained for the Pine audit display.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct BackendPineEvent {
    pub timestamp: String,
    pub action: String,
    pub reason: String,
    pub cs_state: Option<i64>,
    pub trend_state: Option<i64>,
}

/// One named Market Sentiment component projected from the backend ledger.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct BackendPineComponent {
    pub name: String,
    pub value: Option<f64>,
}

/// Latest backend-authored facts for the four-Pine observer.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct BackendPineTelemetry {
    pub candidate_status: Option<String>,
    pub cs_state: Option<i64>,
    pub cs_selected_factor: Option<f64>,
    pub cs_trailing_stop: Option<f64>,
    pub cs_long_onset: Option<bool>,
    pub cs_short_onset: Option<bool>,
    pub trend_state: Option<i64>,
    pub trend_episode_bars: Option<u64>,
    pub trend_episode_high: Option<f64>,
    pub trend_episode_low: Option<f64>,
    pub trend_episode_mid: Option<f64>,
    pub trend_delta_pct: Option<f64>,
    pub trend_ambiguous: Option<bool>,
    pub sentiment_score: Option<f64>,
    pub sentiment_support: Option<u64>,
    pub sentiment_components: Vec<BackendPineComponent>,
    pub tp_density_raw: Option<f64>,
    pub tp_density_score: Option<f64>,
    pub tp_directional_pool: Option<u64>,
    pub tp_minimum_support: Option<u64>,
    pub tp_insufficient_support: Option<bool>,
    pub tp_relative_volume: Option<f64>,
    pub tp_range_position: Option<f64>,
    pub tp_score_semantics: Option<String>,
    pub recent_decisions: Vec<BackendPineEvent>,
}

pub(crate) fn project_pine_stack(rows: &[&LedgerRow]) -> BackendPineTelemetry {
    let decision = rows.iter().rev().find(|row| is_decision(row)).copied();
    BackendPineTelemetry {
        candidate_status: latest_text(rows, "candidate_status"),
        cs_state: signed_integer(decision, "pine_cs_state"),
        cs_selected_factor: number(decision, "pine_cs_selected_factor"),
        cs_trailing_stop: number(decision, "pine_cs_trailing_stop"),
        cs_long_onset: boolean(decision, "pine_cs_long_onset"),
        cs_short_onset: boolean(decision, "pine_cs_short_onset"),
        trend_state: signed_integer(decision, "pine_trend_state"),
        trend_episode_bars: integer(decision, "pine_trend_episode_bars"),
        trend_episode_high: number(decision, "pine_trend_episode_high"),
        trend_episode_low: number(decision, "pine_trend_episode_low"),
        trend_episode_mid: number(decision, "pine_trend_episode_mid"),
        trend_delta_pct: number(decision, "pine_trend_delta_pct"),
        trend_ambiguous: boolean(decision, "pine_trend_ambiguous"),
        sentiment_score: number(decision, "pine_sentiment_score"),
        sentiment_support: integer(decision, "pine_sentiment_support"),
        sentiment_components: sentiment_components(decision),
        tp_density_raw: number(decision, "pine_tp_density_raw"),
        tp_density_score: number(decision, "pine_tp_density_score"),
        tp_directional_pool: integer(decision, "pine_tp_directional_pool"),
        tp_minimum_support: integer(decision, "pine_tp_minimum_support"),
        tp_insufficient_support: boolean(decision, "pine_tp_insufficient_support"),
        tp_relative_volume: number(decision, "pine_tp_relative_volume"),
        tp_range_position: number(decision, "pine_tp_range_position"),
        tp_score_semantics: text(decision, "pine_tp_score_semantics"),
        recent_decisions: recent_decisions(rows),
    }
}

fn recent_decisions(rows: &[&LedgerRow]) -> Vec<BackendPineEvent> {
    const MAX_DECISIONS: usize = 12;
    let mut events: Vec<BackendPineEvent> = rows
        .iter()
        .filter(|row| is_decision(row))
        .map(|row| BackendPineEvent {
            timestamp: row.feed_ts.clone(),
            action: text(Some(row), "decision_action").unwrap_or_else(|| row.action.clone()),
            reason: text(Some(row), "regime_reason").unwrap_or_else(|| "not reported".into()),
            cs_state: signed_integer(Some(row), "pine_cs_state"),
            trend_state: signed_integer(Some(row), "pine_trend_state"),
        })
        .collect();
    let start = events.len().saturating_sub(MAX_DECISIONS);
    events.drain(..start);
    events
}

fn sentiment_components(row: Option<&LedgerRow>) -> Vec<BackendPineComponent> {
    const COMPONENTS: [&str; 11] = [
        "rsi",
        "stochastic",
        "stochastic_rsi",
        "cci",
        "bull_bear_power",
        "moving_average",
        "vwap",
        "bollinger",
        "supertrend",
        "linear_regression",
        "market_structure",
    ];
    let values = row
        .and_then(|value| value.extra.get("pine_sentiment_components"))
        .and_then(Value::as_object);
    COMPONENTS
        .iter()
        .map(|name| BackendPineComponent {
            name: (*name).to_string(),
            value: values
                .and_then(|object| object.get(*name))
                .and_then(Value::as_f64),
        })
        .collect()
}

fn is_decision(row: &LedgerRow) -> bool {
    matches!(row.action.as_str(), "regime_observation" | "regime_history")
        && row.extra.contains_key("pine_cs_state")
}

fn latest_text(rows: &[&LedgerRow], key: &str) -> Option<String> {
    rows.iter().rev().find_map(|row| text(Some(row), key))
}

fn number(row: Option<&LedgerRow>, key: &str) -> Option<f64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_f64)
}

fn integer(row: Option<&LedgerRow>, key: &str) -> Option<u64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_u64)
}

fn signed_integer(row: Option<&LedgerRow>, key: &str) -> Option<i64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_i64)
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
