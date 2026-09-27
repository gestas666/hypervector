//! Private projection of normalized rows into one display snapshot.

use serde_json::Value;

use crate::backend_apex_mm::project_apex_mm;
use crate::backend_cohort::project_cohort;
use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_hulk_smash::project_hulk_smash;
use crate::backend_market::{build_regime_snapshots, latest_book};
use crate::backend_pine_stack::project_pine_stack;

use super::backend_telemetry_portfolio::{build_active_position, build_stats};
use super::backend_telemetry_snapshot_fields::{
    apply_backend_identity, apply_execution_state, apply_funding_rate, apply_live_flags,
    apply_regime_decision, apply_regime_identity, apply_regime_strength, apply_source_observer,
    apply_strategy_configuration, apply_tactical_state,
};
use super::backend_telemetry_trades::{build_trades, is_filled_entry};
use super::{BackendConnectionState, BackendTelemetryError, BackendTelemetrySnapshot, LedgerRow};

#[derive(Default)]
struct LiveProtection {
    state: Option<String>,
    oid: Option<u64>,
    status: Option<String>,
    price: Option<f64>,
    target_oid: Option<u64>,
    target_status: Option<String>,
    target_price: Option<f64>,
    fault: Option<String>,
}

pub(super) fn build_snapshot(
    run_id: String,
    rows: &[&LedgerRow],
) -> Result<BackendTelemetrySnapshot, BackendTelemetryError> {
    let identity = session_identity(rows);
    let leverage = configured_leverage(rows);
    let latest_regime = latest_regime_row(rows);
    let latest_execution = latest_execution_row(rows);
    let protection = live_protection(rows);
    let target_fallback = protection.target_price;
    let mut snapshot = BackendTelemetrySnapshot::disconnected("backend ledger connected");
    snapshot.connection = BackendConnectionState::Connected;
    apply_backend_identity(&mut snapshot, rows, identity);
    apply_strategy_configuration(&mut snapshot, rows);
    apply_regime_identity(&mut snapshot, latest_regime);
    apply_regime_strength(&mut snapshot, latest_regime);
    apply_regime_decision(&mut snapshot, latest_regime);
    apply_source_observer(&mut snapshot, latest_regime);
    apply_live_flags(&mut snapshot, rows);
    apply_tactical_state(&mut snapshot, latest_regime);
    apply_execution_state(
        &mut snapshot,
        latest_regime,
        latest_execution,
        latest_pending_entry_direction(rows),
        target_fallback,
    );
    apply_funding_rate(&mut snapshot, rows, identity);
    apply_strategy_projections(&mut snapshot, rows)?;
    apply_market_projection(&mut snapshot, rows, leverage);
    apply_portfolio_projection(&mut snapshot, &run_id, rows, leverage);
    protection.apply_to(&mut snapshot);
    snapshot.run_id = Some(run_id);
    apply_source_follow_lifecycle_readiness(&mut snapshot);
    Ok(snapshot)
}

impl LiveProtection {
    fn apply_to(self, snapshot: &mut BackendTelemetrySnapshot) {
        snapshot.live_state = self.state;
        snapshot.protective_stop_oid = self.oid;
        snapshot.protective_stop_status = self.status;
        snapshot.protective_stop_price = self.price;
        snapshot.target_order_oid = self.target_oid;
        snapshot.target_order_status = self.target_status;
        snapshot.target_order_price = self.target_price;
        snapshot.latest_fault = self.fault;
    }
}

fn session_identity<'a>(rows: &[&'a LedgerRow]) -> Option<&'a LedgerRow> {
    rows.iter()
        .rev()
        .find(|row| row.action == "session_start")
        .copied()
}

fn configured_leverage(rows: &[&LedgerRow]) -> f64 {
    rows.iter()
        .rev()
        .find_map(|row| row.strategy_params.as_ref())
        .and_then(|params| params.get("leverage"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
}

fn latest_regime_row<'a>(rows: &[&'a LedgerRow]) -> Option<&'a LedgerRow> {
    rows.iter()
        .rev()
        .find(|row| row.action == "regime_observation")
        .copied()
        .or_else(|| {
            rows.iter()
                .rev()
                .find(|row| row.action == "regime_history")
                .copied()
        })
}

fn latest_execution_row<'a>(rows: &[&'a LedgerRow]) -> Option<&'a LedgerRow> {
    rows.iter()
        .rev()
        .find(|row| row.action == "entry_execution_observation")
        .copied()
}

fn apply_strategy_projections(
    snapshot: &mut BackendTelemetrySnapshot,
    rows: &[&LedgerRow],
) -> Result<(), BackendTelemetryError> {
    snapshot.apex_mm = project_apex_mm(rows);
    snapshot.hulk_smash = project_hulk_smash(rows);
    snapshot.pine_stack = project_pine_stack(rows);
    snapshot.cohort =
        project_cohort(rows).map_err(|reason| BackendTelemetryError::InvalidCohort { reason })?;
    snapshot.cohort_checkpoint = CohortCheckpointTelemetry::default();
    Ok(())
}

fn apply_market_projection(
    snapshot: &mut BackendTelemetrySnapshot,
    rows: &[&LedgerRow],
    leverage: f64,
) {
    snapshot.regime_history = rows
        .iter()
        .filter(|row| matches!(row.action.as_str(), "regime_observation" | "regime_history"))
        .filter_map(|row| row.primary_regime.clone())
        .collect();
    snapshot.regime_snapshots = build_regime_snapshots(rows, leverage);
    snapshot.book = latest_book(rows);
}

fn apply_portfolio_projection(
    snapshot: &mut BackendTelemetrySnapshot,
    run_id: &str,
    rows: &[&LedgerRow],
    leverage: f64,
) {
    let trades = build_trades(run_id, rows, leverage);
    let equity: Vec<f64> = rows.iter().filter_map(|row| row.equity).collect();
    let stats = build_stats(rows, &trades, &equity);
    let exit_fee_rate = estimated_exit_fee_rate(rows);
    snapshot.active_position = build_active_position(rows, leverage, exit_fee_rate);
    snapshot.trades = trades;
    snapshot.stats = stats;
    snapshot.equity_history = equity;
}

fn apply_source_follow_lifecycle_readiness(snapshot: &mut BackendTelemetrySnapshot) {
    if !snapshot.is_source_follow() {
        return;
    }
    let entry_pending = snapshot.live_state.as_deref() == Some("ENTRY_PENDING");
    let decision_allowed = snapshot.entry_allowed == Some(true);
    snapshot.entry_allowed = Some(decision_allowed && entry_pending);
    snapshot.pending_entry_direction = if decision_allowed && entry_pending {
        snapshot
            .entry_direction
            .clone()
            .or_else(|| Some("short".to_string()))
    } else {
        None
    };
}

fn live_protection(rows: &[&LedgerRow]) -> LiveProtection {
    let state_row = rows
        .iter()
        .rev()
        .find(|row| row.action == "state_transition")
        .copied();
    let state = state_row
        .and_then(|row| row.extra.get("state"))
        .and_then(Value::as_str)
        .map(str::to_string);
    let oid = state_row
        .and_then(|row| row.extra.get("stop_oid"))
        .and_then(Value::as_u64);
    let (status, price) = oid.map_or((None, None), |value| stop_order(rows, value));
    let target_oid = state_row
        .and_then(|row| row.extra.get("target_oid"))
        .and_then(Value::as_u64);
    let (target_status, target_price) = target_oid.map_or((None, None), |value| {
        resting_order(rows, value, "limit_price", "target_order")
    });
    let fault = rows
        .iter()
        .rev()
        .find(|row| row.action == "fault")
        .and_then(|row| row.extra.get("reason").or_else(|| row.extra.get("message")))
        .and_then(Value::as_str)
        .map(str::to_string);
    LiveProtection {
        state,
        oid,
        status,
        price,
        target_oid,
        target_status,
        target_price,
        fault,
    }
}

fn stop_order(rows: &[&LedgerRow], oid: u64) -> (Option<String>, Option<f64>) {
    let (status, price) = resting_order(rows, oid, "trigger_price", "stop_order");
    (status, price.or_else(|| raised_stop_trigger(rows, oid)))
}

/// Trigger of an acknowledged raise to `oid` before any venue snapshot lists that order.
fn raised_stop_trigger(rows: &[&LedgerRow], oid: u64) -> Option<f64> {
    rows.iter()
        .rev()
        .find(|row| {
            row.action == "protective_stop_raised"
                && row.extra.get("stop_oid").and_then(Value::as_u64) == Some(oid)
        })
        .and_then(|row| row.extra.get("trigger_price"))
        .and_then(Value::as_f64)
        .filter(|price| price.is_finite() && *price > 0.0)
}

fn resting_order(
    rows: &[&LedgerRow],
    oid: u64,
    price_key: &str,
    action: &str,
) -> (Option<String>, Option<f64>) {
    for row in rows.iter().rev() {
        let Some(orders) = row.extra.get("open_orders").and_then(Value::as_array) else {
            continue;
        };
        if let Some(order) = orders
            .iter()
            .find(|order| order.get("oid").and_then(Value::as_u64) == Some(oid))
        {
            let price = order.get(price_key).and_then(Value::as_f64);
            return (Some("RESTING".to_string()), price);
        }
    }
    let status = rows
        .iter()
        .rev()
        .find(|row| row.action == action)
        .filter(|row| row.extra.get("oid").and_then(Value::as_u64) == Some(oid))
        .and_then(|row| row.extra.get("status"))
        .and_then(Value::as_str)
        .map(str::to_uppercase);
    (status, None)
}

fn estimated_exit_fee_rate(rows: &[&LedgerRow]) -> f64 {
    let costs = rows.iter().rev().find_map(|row| row.costs.as_ref());
    let execution = rows.iter().rev().find_map(|row| row.execution.as_ref());
    let is_market = execution
        .and_then(|value| value.get("order_type"))
        .and_then(Value::as_str)
        == Some("market");
    let key = if is_market {
        "taker_fee_rate"
    } else {
        "maker_fee_rate"
    };
    costs
        .and_then(|value| value.get(key))
        .and_then(Value::as_f64)
        .or_else(|| {
            costs
                .and_then(|value| value.get("taker_fee_rate"))
                .and_then(Value::as_f64)
        })
        .unwrap_or(0.0)
}

fn latest_pending_entry_direction(rows: &[&LedgerRow]) -> Option<String> {
    let mut pending = None;
    for row in rows {
        match row.action.as_str() {
            "submit_entry" => {
                pending = row
                    .extra
                    .get("side")
                    .and_then(Value::as_str)
                    .and_then(entry_direction_from_side);
            }
            "cancel_entry" | "rejected_entry" => pending = None,
            "enter_long" | "enter_short" if is_filled_entry(row) => pending = None,
            _ => {}
        }
    }
    pending
}

fn entry_direction_from_side(side: &str) -> Option<String> {
    match side {
        "buy" => Some("long".to_string()),
        "sell" => Some("short".to_string()),
        _ => None,
    }
}
