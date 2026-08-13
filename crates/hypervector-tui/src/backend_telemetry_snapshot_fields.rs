//! Cohesive field projections for backend telemetry snapshots.

use serde_json::Value;

use super::{BackendTelemetrySnapshot, LedgerRow};

pub(super) fn apply_backend_identity(
    snapshot: &mut BackendTelemetrySnapshot,
    rows: &[&LedgerRow],
    identity: Option<&LedgerRow>,
) {
    snapshot.export_id = latest_value(rows, |row| row.export_id.clone())
        .or_else(|| identity.and_then(|row| row.export_id.clone()));
    snapshot.data_root = latest_value(rows, |row| row.data_root.clone());
    snapshot.symbol = latest_value(rows, |row| row.symbol.clone());
    snapshot.profile_id = latest_value(rows, |row| row.profile_id.clone());
    snapshot.profile_fingerprint = latest_value(rows, |row| row.profile_fingerprint.clone());
    snapshot.capital_source = latest_value(rows, |row| row.capital_source.clone());
    snapshot.portfolio_purpose = latest_value(rows, |row| row.portfolio_purpose.clone());
    snapshot.backend_ledger_path = latest_value(rows, |row| row.backend_ledger_path.clone());
    snapshot.strategy_name = latest_value(rows, |row| row.strategy_name.clone());
}

pub(super) fn apply_strategy_configuration(
    snapshot: &mut BackendTelemetrySnapshot,
    rows: &[&LedgerRow],
) {
    snapshot.execution_mode = latest_value(rows, |row| row.execution_mode.clone());
    snapshot.metalabel_mode = latest_value(rows, |row| row.metalabel_mode.clone());
    snapshot.metalabel_policy =
        latest_value(rows, |row| row.metalabel_policy.clone()).unwrap_or(Value::Null);
    snapshot.metalabel_bundle_id = latest_value(rows, |row| row.metalabel_bundle_id.clone());
    snapshot.latest_metalabel_p = rows.iter().rev().find_map(|row| row.metalabel_p);
    snapshot.latest_conviction_source = latest_value(rows, |row| row.conviction_source.clone());
    snapshot.strategy_params =
        latest_value(rows, |row| row.strategy_params.clone()).unwrap_or(Value::Null);
    snapshot.exits = latest_value(rows, |row| row.exits.clone()).unwrap_or(Value::Null);
    snapshot.risk = latest_value(rows, |row| row.risk.clone()).unwrap_or(Value::Null);
    snapshot.execution_policy =
        latest_value(rows, |row| row.execution.clone()).unwrap_or(Value::Null);
    snapshot.position_policy =
        latest_value(rows, |row| row.position_policy.clone()).unwrap_or(Value::Null);
    snapshot.regime_policy =
        latest_value(rows, |row| row.regime_policy.clone()).unwrap_or(Value::Null);
    snapshot.observer_policies =
        latest_value(rows, |row| row.observer_policies.clone()).unwrap_or(Value::Null);
    snapshot.costs = latest_value(rows, |row| row.costs.clone()).unwrap_or(Value::Null);
    snapshot.runtime = latest_value(rows, |row| row.runtime.clone()).unwrap_or(Value::Null);
    snapshot.orderbook_archive =
        latest_value(rows, |row| row.orderbook_archive.clone()).unwrap_or(Value::Null);
}

pub(super) fn apply_regime_identity(
    snapshot: &mut BackendTelemetrySnapshot,
    latest: Option<&LedgerRow>,
) {
    snapshot.latest_regime = latest.and_then(|row| row.primary_regime.clone());
    snapshot.latest_regime_feed_ts = latest.map(|row| row.feed_ts.clone());
    snapshot.latest_regime_reason = latest
        .and_then(|row| row.extra.get("regime_reason"))
        .and_then(Value::as_str)
        .map(str::to_string);
    snapshot.latest_regime_confidence = latest
        .and_then(|row| row.extra.get("confidence"))
        .and_then(Value::as_f64);
}

pub(super) fn apply_regime_strength(
    snapshot: &mut BackendTelemetrySnapshot,
    latest: Option<&LedgerRow>,
) {
    snapshot.latest_regime_strength_score = latest
        .and_then(|row| row.extra.get("regime_strength_score"))
        .and_then(Value::as_f64)
        .or_else(|| {
            latest
                .and_then(|row| row.extra.get("confidence"))
                .and_then(Value::as_f64)
        });
    snapshot.latest_regime_score_source = latest
        .and_then(|row| row.extra.get("regime_score_source"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .or_else(|| {
            latest
                .and_then(|row| row.extra.get("confidence"))
                .and_then(Value::as_f64)
                .map(|_| "legacy_confidence_alias".to_string())
        });
}

pub(super) fn apply_regime_decision(
    snapshot: &mut BackendTelemetrySnapshot,
    latest: Option<&LedgerRow>,
) {
    snapshot.source_follow_signal_range_bps = latest
        .and_then(|row| row.extra.get("source_follow_signal_range_bps"))
        .and_then(Value::as_f64);
    snapshot.structural_direction = text_extra(latest, "structural_direction");
    snapshot.entry_direction = text_extra(latest, "entry_direction");
    snapshot.entry_allowed = latest
        .and_then(|row| row.extra.get("entry_allowed"))
        .and_then(Value::as_bool);
    snapshot.regime_admitted = latest
        .and_then(|row| row.extra.get("regime_admitted"))
        .and_then(Value::as_bool);
    snapshot.latest_decision_action = text_extra(latest, "decision_action");
}

pub(super) fn apply_source_observer(
    snapshot: &mut BackendTelemetrySnapshot,
    latest: Option<&LedgerRow>,
) {
    snapshot.source_long_observer = latest
        .and_then(|row| row.extra.get("source_long_observer"))
        .filter(|value| !value.is_null())
        .cloned();
    snapshot.source_long_observer_signal_time = text_extra(latest, "available_at_utc");
    snapshot.source_long_forward = None;
}

pub(super) fn apply_live_flags(snapshot: &mut BackendTelemetrySnapshot, rows: &[&LedgerRow]) {
    snapshot.wallet_configured = latest_value(rows, |row| row.wallet_configured);
    snapshot.signing_key_configured = latest_value(rows, |row| row.signing_key_configured);
    snapshot.live_enabled = latest_value(rows, |row| row.live_enabled);
    snapshot.live_armed = latest_value(rows, |row| row.live_armed);
    snapshot.execution_authority = rows
        .iter()
        .rev()
        .find_map(|row| row.extra.get("execution_authority"))
        .and_then(Value::as_str)
        .map(str::to_string);
}

pub(super) fn apply_tactical_state(
    snapshot: &mut BackendTelemetrySnapshot,
    latest: Option<&LedgerRow>,
) {
    snapshot.compression_ready = bool_extra(latest, "compression_ready");
    snapshot.bbwp_compression_threshold = number_extra(latest, "bbwp_compression_threshold");
    snapshot.ema_gap_bps_signed = number_extra(latest, "ema_gap_bps_signed");
    snapshot.rsi_ema = number_extra(latest, "rsi_ema");
    snapshot.rsi_cross_direction = text_extra(latest, "rsi_cross_direction");
    snapshot.tactical_breakout_direction = text_extra(latest, "tactical_breakout_direction");
    snapshot.breakout_volume_ratio = number_extra(latest, "breakout_volume_ratio");
    snapshot.prior_range_high = number_extra(latest, "prior_range_high");
    snapshot.prior_range_low = number_extra(latest, "prior_range_low");
}

pub(super) fn apply_execution_state(
    snapshot: &mut BackendTelemetrySnapshot,
    latest_regime: Option<&LedgerRow>,
    latest_execution: Option<&LedgerRow>,
    pending_direction: Option<String>,
    target_fallback: Option<f64>,
) {
    snapshot.pending_entry_direction = pending_direction;
    snapshot.pending_maker_limit_price =
        number_extra(latest_execution, "pending_maker_limit_price");
    snapshot.active_target_prices = latest_execution
        .and_then(|row| row.extra.get("active_target_prices"))
        .and_then(Value::as_array)
        .or_else(|| {
            latest_regime
                .and_then(|row| row.extra.get("active_target_prices"))
                .and_then(Value::as_array)
        })
        .map(|values| values.iter().filter_map(Value::as_f64).collect())
        .or_else(|| target_fallback.map(|price| vec![price]))
        .unwrap_or_default();
    let execution_or_regime = latest_execution.or(latest_regime);
    snapshot.entry_retry_state = text_extra(execution_or_regime, "entry_retry_state");
    snapshot.entry_cooldown_active = bool_extra(execution_or_regime, "entry_cooldown_active");
}

pub(super) fn apply_funding_rate(
    snapshot: &mut BackendTelemetrySnapshot,
    rows: &[&LedgerRow],
    identity: Option<&LedgerRow>,
) {
    snapshot.funding_rate_hourly = rows
        .iter()
        .rev()
        .find_map(|row| row.extra.get("funding_rate_hourly"))
        .and_then(Value::as_f64)
        .or_else(|| {
            identity
                .and_then(|row| row.costs.as_ref())
                .and_then(|costs| costs.get("funding_rate_hourly"))
                .and_then(Value::as_f64)
        });
}

fn latest_value<T>(rows: &[&LedgerRow], get: impl Fn(&LedgerRow) -> Option<T>) -> Option<T> {
    rows.iter().rev().find_map(|row| get(row))
}

fn text_extra(row: Option<&LedgerRow>, key: &str) -> Option<String> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn number_extra(row: Option<&LedgerRow>, key: &str) -> Option<f64> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_f64)
}

fn bool_extra(row: Option<&LedgerRow>, key: &str) -> Option<bool> {
    row.and_then(|value| value.extra.get(key))
        .and_then(Value::as_bool)
}
