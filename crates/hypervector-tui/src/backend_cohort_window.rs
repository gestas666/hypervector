//! Bounded latest-run projection for the append-only multi-asset cohort ledger.

use std::collections::{BTreeMap, HashSet};

use serde::Deserialize;
use serde_json::{Map, Value, json};

use super::BackendTelemetryError;

const SNAPSHOT_LIMIT: usize = 90;
const CANDLE_LIMIT: usize = 360;
const ACTION_LIMIT: usize = 50;
const WITHHELD_LIMIT: usize = 50;
const REGIME_HISTORY_LIMIT: usize = 240;
const STRATEGY_INTENT_LIMIT: usize = 50;
const OPERATOR_EVENT_LIMIT: usize = 30;
const MAXIMUM_HOLD_EVENT_LIMIT: usize = 50;
const CANONICAL_REGIME_PROVIDER: &str = "canonical_regime_telemetry_v1";
const LEGACY_REGIME_PROVIDER: &str = "range_onset_bidirectional_v1";

#[derive(Deserialize)]
struct EventEnvelope {
    event_type: Option<String>,
    run_id: Option<String>,
}

struct RetainedRow {
    index: usize,
    content: String,
}

struct RoutingWindow {
    actions_remaining: usize,
    withheld_remaining: usize,
    latest_evaluations: HashSet<String>,
    regime_decisions: HashSet<String>,
}

struct CohortWindow {
    rows: Vec<RetainedRow>,
    run_ids: HashSet<String>,
    snapshots: usize,
    strategy_intents: usize,
    operator_events: usize,
    maximum_hold_events: usize,
    market_book_retained: bool,
    heartbeat_retained: bool,
    terminal_events: HashSet<String>,
    unsupported_event: bool,
    routing: RoutingWindow,
    candle_template: Option<(usize, Value)>,
    candles: BTreeMap<String, Vec<Value>>,
}

impl Default for CohortWindow {
    fn default() -> Self {
        Self {
            rows: Vec::new(),
            run_ids: HashSet::new(),
            snapshots: 0,
            strategy_intents: 0,
            operator_events: 0,
            maximum_hold_events: 0,
            market_book_retained: false,
            heartbeat_retained: false,
            terminal_events: HashSet::new(),
            unsupported_event: false,
            routing: RoutingWindow {
                actions_remaining: ACTION_LIMIT,
                withheld_remaining: WITHHELD_LIMIT,
                latest_evaluations: HashSet::new(),
                regime_decisions: HashSet::new(),
            },
            candle_template: None,
            candles: BTreeMap::new(),
        }
    }
}

/// Compact only the newest cohort run while preserving its displayed state.
pub(super) fn compact_latest_cohort(
    content: &str,
) -> Result<Option<String>, BackendTelemetryError> {
    let lines = content.lines().collect::<Vec<_>>();
    let mut window = CohortWindow::default();
    for (index, line) in lines.iter().enumerate().rev() {
        if line.trim().is_empty() {
            continue;
        }
        let envelope = parse_envelope(line, index + 1)?;
        if let Some(run_id) = envelope.run_id.as_ref() {
            window.run_ids.insert(run_id.clone());
        }
        if envelope.event_type.as_deref() == Some("configuration_identity") {
            return window.finish_identity(index, line, envelope.run_id, index + 1);
        }
        window.capture(index, line, envelope.event_type.as_deref(), index + 1)?;
    }
    Ok(None)
}

impl CohortWindow {
    fn capture(
        &mut self,
        index: usize,
        line: &str,
        event_type: Option<&str>,
        line_number: usize,
    ) -> Result<(), BackendTelemetryError> {
        match event_type {
            Some("cohort_snapshot") => self.retain_snapshot(index, line),
            Some("market_candles") => self.capture_candles(index, line, line_number)?,
            Some("intent_routing") => self.capture_routing(index, line, line_number)?,
            Some("canonical_regime_evaluations") => {
                self.capture_canonical_regimes(index, line, line_number)?
            }
            Some("strategy_intent") => self.retain_strategy_intent(index, line),
            Some("operator_command") => self.retain_operator_event(index, line),
            Some("maximum_hold_decision") => self.retain_maximum_hold_event(index, line),
            Some(event @ ("runtime_stopped" | "runtime_fault")) => {
                self.retain_terminal(index, line, event)
            }
            Some("market_books") if !self.market_book_retained => {
                self.retain(index, line);
                self.market_book_retained = true;
            }
            Some("heartbeat") if !self.heartbeat_retained => {
                self.retain(index, line);
                self.heartbeat_retained = true;
            }
            Some("funding_reconciliation_window") => {}
            Some("market_books" | "heartbeat") => {}
            _ => self.unsupported_event = true,
        }
        Ok(())
    }

    fn retain_terminal(&mut self, index: usize, line: &str, event: &str) {
        if self.terminal_events.insert(event.to_owned()) {
            self.retain(index, line);
        }
    }

    fn retain_snapshot(&mut self, index: usize, line: &str) {
        if self.snapshots < SNAPSHOT_LIMIT {
            self.retain(index, line);
            self.snapshots += 1;
        }
    }

    fn retain_strategy_intent(&mut self, index: usize, line: &str) {
        if self.strategy_intents < STRATEGY_INTENT_LIMIT {
            self.retain(index, line);
            self.strategy_intents += 1;
        }
    }

    fn retain_operator_event(&mut self, index: usize, line: &str) {
        if self.operator_events < OPERATOR_EVENT_LIMIT {
            self.retain(index, line);
            self.operator_events += 1;
        }
    }

    fn retain_maximum_hold_event(&mut self, index: usize, line: &str) {
        if self.maximum_hold_events < MAXIMUM_HOLD_EVENT_LIMIT {
            self.retain(index, line);
            self.maximum_hold_events += 1;
        }
    }

    fn capture_candles(
        &mut self,
        index: usize,
        line: &str,
        line_number: usize,
    ) -> Result<(), BackendTelemetryError> {
        if candles_saturated(&self.candles) {
            return Ok(());
        }
        let value = parse_value(line, line_number)?;
        let bars = payload_object(&value, "market_candles")?
            .get("bars")
            .and_then(Value::as_object)
            .ok_or_else(|| invalid_cohort("market_candles bars must be an object"))?;
        for (symbol, values) in bars {
            let values = values
                .as_array()
                .ok_or_else(|| invalid_cohort("market_candles symbol bars must be arrays"))?;
            retain_reverse(&mut self.candles, symbol, values, CANDLE_LIMIT);
        }
        if self.candle_template.is_none() {
            self.candle_template = Some((index, value));
        }
        Ok(())
    }

    fn capture_routing(
        &mut self,
        index: usize,
        line: &str,
        line_number: usize,
    ) -> Result<(), BackendTelemetryError> {
        let mut value = parse_value(line, line_number)?;
        let payload = payload_object_mut(&mut value, "intent_routing")?;
        let actions = required_array(payload, "actions", "intent_routing")?;
        let withheld = required_array(payload, "withheld", "intent_routing")?;
        let evaluations = optional_array(payload, "evaluations", "intent_routing")?;
        let actions = take_newest(actions, &mut self.routing.actions_remaining);
        let withheld = take_newest(withheld, &mut self.routing.withheld_remaining);
        let evaluations = self.routing.take_evaluations(evaluations)?;
        let retained = !actions.is_empty() || !withheld.is_empty() || !evaluations.is_empty();
        payload.insert("actions".into(), Value::Array(actions));
        payload.insert("withheld".into(), Value::Array(withheld));
        payload.insert("evaluations".into(), Value::Array(evaluations));
        if retained {
            self.rows.push(RetainedRow {
                index,
                content: value.to_string(),
            });
        }
        Ok(())
    }

    fn capture_canonical_regimes(
        &mut self,
        index: usize,
        line: &str,
        line_number: usize,
    ) -> Result<(), BackendTelemetryError> {
        let mut value = parse_value(line, line_number)?;
        let payload = payload_object_mut(&mut value, "canonical_regime_evaluations")?;
        let evaluations = required_array(payload, "evaluations", "canonical_regime_evaluations")?;
        let evaluations = self.routing.take_evaluations(evaluations)?;
        payload.insert("evaluations".into(), Value::Array(evaluations.clone()));
        if !evaluations.is_empty() {
            self.rows.push(RetainedRow {
                index,
                content: value.to_string(),
            });
        }
        Ok(())
    }

    fn finish_identity(
        mut self,
        index: usize,
        line: &str,
        run_id: Option<String>,
        line_number: usize,
    ) -> Result<Option<String>, BackendTelemetryError> {
        let identity = parse_value(line, line_number)?;
        if identity_strategy(&identity) != Some("multi_asset_bidirectional_cohort") {
            return Ok(None);
        }
        if self.unsupported_event || !single_run(&self.run_ids, run_id.as_deref()) {
            return Ok(None);
        }
        if !self.finish_candles(&identity)? {
            return Ok(None);
        }
        self.rows.push(RetainedRow {
            index,
            content: line.to_string(),
        });
        self.rows.sort_by_key(|row| row.index);
        Ok(Some(
            self.rows
                .into_iter()
                .map(|row| row.content)
                .collect::<Vec<_>>()
                .join("\n"),
        ))
    }

    fn finish_candles(&mut self, identity: &Value) -> Result<bool, BackendTelemetryError> {
        let Some((index, mut template)) = self.candle_template.take() else {
            return Ok(true);
        };
        let symbols = identity_symbols(identity)?;
        if symbols
            .iter()
            .any(|symbol| !self.candles.contains_key(symbol))
        {
            return Ok(false);
        }
        let mut bars = Map::new();
        for symbol in symbols {
            let mut values = self.candles.remove(&symbol).unwrap_or_default();
            values.reverse();
            bars.insert(symbol, Value::Array(values));
        }
        let payload = payload_object_mut(&mut template, "market_candles")?;
        payload.insert("timeframe".into(), json!("1m"));
        payload.insert("bars".into(), Value::Object(bars));
        self.rows.push(RetainedRow {
            index,
            content: template.to_string(),
        });
        Ok(true)
    }

    fn retain(&mut self, index: usize, line: &str) {
        self.rows.push(RetainedRow {
            index,
            content: line.to_string(),
        });
    }
}

impl RoutingWindow {
    fn take_evaluations(
        &mut self,
        evaluations: &[Value],
    ) -> Result<Vec<Value>, BackendTelemetryError> {
        let mut selected = Vec::new();
        for evaluation in evaluations.iter().rev() {
            let object = evaluation
                .as_object()
                .ok_or_else(|| invalid_cohort("provider evaluation must be an object"))?;
            let strategy = required_text(object, "strategy_id", "provider evaluation")?;
            let symbol = required_text(object, "symbol", "provider evaluation")?;
            let decision = required_u64(object, "decision_time_ms", "provider evaluation")?;
            let pair = format!("{strategy}:{symbol}");
            let newest_pair = self.latest_evaluations.insert(pair);
            let regime_key = format!("{symbol}:{decision}");
            let recent_regime = is_regime_provider(strategy)
                && self.regime_decisions.len() < REGIME_HISTORY_LIMIT
                && self.regime_decisions.insert(regime_key);
            if newest_pair || recent_regime {
                selected.push(evaluation.clone());
            }
        }
        selected.reverse();
        Ok(selected)
    }
}

fn is_regime_provider(strategy: &str) -> bool {
    matches!(strategy, CANONICAL_REGIME_PROVIDER | LEGACY_REGIME_PROVIDER)
}

fn parse_envelope(line: &str, line_number: usize) -> Result<EventEnvelope, BackendTelemetryError> {
    serde_json::from_str(line).map_err(|source| BackendTelemetryError::InvalidJson {
        line: line_number,
        source,
    })
}

fn parse_value(line: &str, line_number: usize) -> Result<Value, BackendTelemetryError> {
    serde_json::from_str(line).map_err(|source| BackendTelemetryError::InvalidJson {
        line: line_number,
        source,
    })
}

fn payload_object<'a>(
    value: &'a Value,
    label: &str,
) -> Result<&'a Map<String, Value>, BackendTelemetryError> {
    value
        .get("payload")
        .and_then(Value::as_object)
        .ok_or_else(|| invalid_cohort(&format!("{label} payload must be an object")))
}

fn payload_object_mut<'a>(
    value: &'a mut Value,
    label: &str,
) -> Result<&'a mut Map<String, Value>, BackendTelemetryError> {
    value
        .get_mut("payload")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| invalid_cohort(&format!("{label} payload must be an object")))
}

fn required_array<'a>(
    payload: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a [Value], BackendTelemetryError> {
    payload
        .get(key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| invalid_cohort(&format!("{label} {key} must be an array")))
}

fn optional_array<'a>(
    payload: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a [Value], BackendTelemetryError> {
    match payload.get(key) {
        None => Ok(&[]),
        Some(value) => value
            .as_array()
            .map(Vec::as_slice)
            .ok_or_else(|| invalid_cohort(&format!("{label} {key} must be an array"))),
    }
}

fn take_newest(values: &[Value], remaining: &mut usize) -> Vec<Value> {
    let count = values.len().min(*remaining);
    *remaining -= count;
    values[values.len() - count..].to_vec()
}

fn retain_reverse(
    target: &mut BTreeMap<String, Vec<Value>>,
    symbol: &str,
    values: &[Value],
    limit: usize,
) {
    let retained = target.entry(symbol.to_string()).or_default();
    let remaining = limit.saturating_sub(retained.len());
    retained.extend(values.iter().rev().take(remaining).cloned());
}

fn candles_saturated(candles: &BTreeMap<String, Vec<Value>>) -> bool {
    !candles.is_empty() && candles.values().all(|values| values.len() >= CANDLE_LIMIT)
}

fn identity_strategy(identity: &Value) -> Option<&str> {
    identity
        .get("payload")
        .and_then(|payload| payload.get("strategy_name"))
        .and_then(Value::as_str)
}

fn identity_symbols(identity: &Value) -> Result<Vec<String>, BackendTelemetryError> {
    payload_object(identity, "configuration_identity")?
        .get("enabled_symbols")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_cohort("configuration identity requires enabled_symbols"))?
        .iter()
        .map(|value| {
            value
                .as_str()
                .map(str::to_string)
                .ok_or_else(|| invalid_cohort("enabled_symbols must contain strings"))
        })
        .collect()
}

fn single_run(run_ids: &HashSet<String>, identity_run: Option<&str>) -> bool {
    identity_run.is_some_and(|run_id| run_ids.len() == 1 && run_ids.contains(run_id))
}

fn required_text<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a str, BackendTelemetryError> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| invalid_cohort(&format!("{label} requires text {key}")))
}

fn required_u64(
    object: &Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<u64, BackendTelemetryError> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_cohort(&format!("{label} requires integer {key}")))
}

fn invalid_cohort(reason: &str) -> BackendTelemetryError {
    BackendTelemetryError::InvalidCohort {
        reason: reason.to_string(),
    }
}

#[cfg(test)]
#[path = "backend_cohort_window_tests.rs"]
mod tests;
