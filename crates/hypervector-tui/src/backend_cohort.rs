//! Strict projection of the multi-asset cohort's authoritative ledger events.

#[path = "backend_cohort_routing.rs"]
mod routing;
#[path = "backend_cohort_validation.rs"]
mod validation;

use std::collections::BTreeMap;

use serde::Deserialize;
use serde::de::DeserializeOwned;
use serde_json::Value;

pub use crate::backend_cohort_book::{CohortBookLevel, CohortBookSnapshot};
use crate::backend_cohort_candles::candle_history;
pub use crate::backend_cohort_health::CohortHeartbeat;
pub use crate::backend_cohort_operator::{CohortOperatorEvent, CohortTransitionDrainTelemetry};
pub use crate::backend_cohort_readiness::{
    CohortProviderEvaluation, CohortSetupCoverage, CohortSignalReadiness,
};
pub use crate::backend_cohort_strategy_evidence::CohortStrategyEvidence;
use crate::backend_telemetry::LedgerRow;
pub use routing::{CohortRoutingAction, CohortWithheldIntent};
use validation::{project_identity, validate_snapshot};

/// Shared-account totals from the latest backend reconciliation cycle.
#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
pub struct CohortAccount {
    pub account_value_usd: f64,
    pub withdrawable_usd: f64,
    pub total_margin_used_usd: f64,
    pub total_notional_position_usd: f64,
    pub open_position_count: usize,
    pub account_balance_source: Option<String>,
}

/// Effective execution envelope for one enabled venue asset.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortAssetConfig {
    pub symbol: String,
    pub sides: Vec<String>,
    pub leverage: f64,
    pub venue_max_leverage: f64,
    pub margin_fraction: f64,
    pub max_notional_usd: f64,
    #[serde(default)]
    pub entry_slippage_cap_fraction: Option<f64>,
    #[serde(default)]
    pub market_slippage_cap_fraction: Option<f64>,
    pub stop_bps: f64,
    pub maximum_hold_seconds: u64,
}

/// Provider-specific execution mechanics persisted with one open position.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortExecutionPlan {
    pub strategy_id: String,
    pub entry_liquidity: String,
    pub stop_policy: String,
    pub target_policy: String,
    pub maximum_hold_seconds: u64,
    pub stop_bps: Option<f64>,
    pub minimum_stop_bps: Option<f64>,
    pub maximum_stop_bps: Option<f64>,
    pub target_bps: Option<f64>,
    pub target_r_multiple: Option<f64>,
    pub safety_stop_overlay: bool,
    pub stop_anchor: Option<f64>,
    #[serde(default)]
    pub target_anchor: Option<f64>,
    #[serde(default = "fixed_maximum_hold_policy")]
    pub maximum_hold_policy: String,
    #[serde(default)]
    pub hard_maximum_hold_seconds: Option<u64>,
    #[serde(default = "ignored_provider_recipe_exit_policy")]
    pub provider_recipe_exit_policy: String,
    #[serde(default = "disabled_profit_lock_policy")]
    pub profit_lock_policy: String,
    #[serde(default)]
    pub profit_lock_activation_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_floor_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_giveback_bps: Option<f64>,
}

/// Configured execution mechanics for one signal provider.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortProviderExecutionContract {
    pub entry_liquidity: String,
    pub stop_policy: String,
    pub target_policy: String,
    pub maximum_hold_seconds: u64,
    pub stop_bps: Option<f64>,
    pub minimum_stop_bps: Option<f64>,
    pub maximum_stop_bps: Option<f64>,
    pub target_bps: Option<f64>,
    pub target_r_multiple: Option<f64>,
    pub safety_stop_overlay: bool,
    #[serde(default = "fixed_maximum_hold_policy")]
    pub maximum_hold_policy: String,
    #[serde(default)]
    pub hard_maximum_hold_seconds: Option<u64>,
    #[serde(default = "ignored_provider_recipe_exit_policy")]
    pub provider_recipe_exit_policy: String,
    #[serde(default = "disabled_profit_lock_policy")]
    pub profit_lock_policy: String,
    #[serde(default)]
    pub profit_lock_activation_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_floor_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_giveback_bps: Option<f64>,
}

fn fixed_maximum_hold_policy() -> String {
    "fixed".into()
}

fn ignored_provider_recipe_exit_policy() -> String {
    "ignore".into()
}

fn disabled_profit_lock_policy() -> String {
    "none".into()
}

pub(crate) fn profit_lock_contract_valid(
    strategy_id: Option<&str>,
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
) -> bool {
    if matches!(
        policy,
        "btc_hulk_delayed_component_floor_v1" | "btc_hulk_delayed_component_exit_v2"
    ) {
        return strategy_id == Some("hulk_expansion_short_robust_v3")
            && activation.is_none()
            && floor.is_none()
            && giveback.is_none();
    }
    if policy == "none" {
        return activation.is_none() && floor.is_none() && giveback.is_none();
    }
    let (Some(activation), Some(floor), Some(giveback)) = (activation, floor, giveback) else {
        return false;
    };
    policy == "completed_bar_trailing"
        && [activation, floor, giveback]
            .iter()
            .all(|value| value.is_finite() && *value > 0.0)
        && floor <= activation
}

#[cfg(test)]
#[path = "backend_cohort_tests.rs"]
mod tests;

/// Provider-specific entry sizing bounded by the asset adapter ceiling.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortProviderSizing {
    pub margin_fraction: f64,
    pub max_notional_usd: f64,
}

/// Effective bidirectional provider declaration.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortProvider {
    pub strategy_id: String,
    pub symbols: Vec<String>,
    pub sides: Vec<String>,
    pub priority: i64,
    pub timeframe: String,
    pub maximum_entry_delay_seconds: u64,
    #[serde(default)]
    pub execution_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub execution_side_overrides: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    pub entry_context_overrides: BTreeMap<String, String>,
    #[serde(default)]
    pub sizing_overrides: BTreeMap<String, CohortProviderSizing>,
    #[serde(default)]
    pub source_profile: Option<String>,
    #[serde(default)]
    pub execution: Option<CohortProviderExecutionContract>,
}

/// Effective backend polling and history settings.
#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
pub struct CohortRuntimeConfig {
    pub poll_seconds: f64,
    pub lookback_days: usize,
}

/// Verified source/config/data bundle created before live authority existed.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortPrestartBackupEvidence {
    pub status: String,
    pub bundle_path: String,
    pub manifest_path: String,
    pub manifest_sha256: String,
    pub strategy_changed: bool,
    pub implementation_file_count: usize,
    pub implementation_sha256: String,
}

/// Backend-authored canonical-regime authority in the intent router.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortRoutingPolicy {
    pub mode: String,
    pub alignment_basis: String,
    pub state_weights: BTreeMap<String, f64>,
    pub standalone_intents_ungated: bool,
    pub forced_regime_exit: bool,
    pub fallback: String,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
struct CohortPositionPolicy {
    max_positions_per_symbol: usize,
    maximum_concurrent_positions: usize,
}

/// Venue-backed position and lifecycle state for one coin.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortAssetSnapshot {
    pub symbol: String,
    pub state: String,
    pub direction_capability: Vec<String>,
    pub position_size_signed: f64,
    pub position_side: Option<String>,
    pub entry_oid: Option<u64>,
    pub stop_oid: Option<u64>,
    pub target_oid: Option<u64>,
    pub target_price: Option<f64>,
    pub execution_plan: Option<CohortExecutionPlan>,
    pub last_fault: Option<String>,
    pub mark_price: Option<f64>,
    #[serde(default)]
    pub market_reference_price: Option<f64>,
    #[serde(default)]
    pub mark_price_source: Option<String>,
    pub entry_price: Option<f64>,
    pub liquidation_price: Option<f64>,
    pub liquidation_distance_pct: Option<f64>,
    pub margin_used_usd: f64,
    pub position_value_usd: f64,
    pub unrealized_pnl_usd: f64,
    pub leverage: Option<u64>,
    pub fees_net_usd: Option<f64>,
    pub funding_net_usd: Option<f64>,
    pub realized_pnl_usd: Option<f64>,
    pub fill_count: Option<usize>,
    #[serde(default)]
    pub cost_scope: Option<String>,
}

impl CohortAssetSnapshot {
    /// Align position economics to the venue account snapshot timestamp.
    pub fn reconcile_position_mark(&mut self) -> Result<(), String> {
        let market_reference = self.market_reference_price.or(self.mark_price);
        self.market_reference_price = market_reference;
        if self.position_size_signed == 0.0 {
            self.mark_price_source = Some("market_reference".into());
            return Ok(());
        }
        let mark = self.position_value_usd / self.position_size_signed.abs();
        if !mark.is_finite() || mark <= 0.0 {
            return Err(format!(
                "{} open position has invalid venue-implied mark",
                self.symbol
            ));
        }
        self.mark_price = Some(mark);
        self.mark_price_source = Some("venue_position_value_div_size".into());
        self.liquidation_distance_pct = self
            .liquidation_price
            .map(|liquidation| (liquidation - mark).abs() / mark * 100.0);
        Ok(())
    }
}

/// One exact venue fill plus backend-derived execution-quality measurements.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortFill {
    pub symbol: String,
    pub strategy_id: String,
    #[serde(default)]
    pub exit_controller_id: Option<String>,
    #[serde(default)]
    pub origin_run_id: Option<String>,
    pub operation: String,
    pub trade_id: u64,
    pub oid: u64,
    pub venue_timestamp_ms: u64,
    pub price: f64,
    pub size: f64,
    pub side: String,
    pub direction: String,
    pub fee_usd: f64,
    pub closed_pnl_usd: f64,
    pub expected_price: Option<f64>,
    pub slippage_bps: Option<f64>,
    pub acknowledgement_latency_ms: Option<u64>,
    pub markout_bps: Option<f64>,
    pub markout_horizon_ms: Option<u64>,
    #[serde(default)]
    pub entry_price: Option<f64>,
    #[serde(default)]
    pub entry_venue_timestamp_ms: Option<u64>,
    #[serde(default)]
    pub lifecycle_fees_usd: Option<f64>,
    #[serde(default)]
    pub lifecycle_funding_usd: Option<f64>,
    #[serde(default)]
    pub net_pnl_usd: Option<f64>,
    #[serde(default)]
    pub holding_time_ms: Option<u64>,
    pub exit_reason: Option<String>,
}

/// One backend-authored completed Hyperliquid 1-minute candle.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortCandle {
    pub timestamp_ms: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct CohortSnapshotPayload {
    account_value_usd: f64,
    withdrawable_usd: f64,
    total_margin_used_usd: f64,
    total_notional_position_usd: f64,
    open_position_count: usize,
    #[serde(default)]
    account_balance_source: Option<String>,
    assets: Vec<CohortAssetSnapshot>,
    recent_fills: Vec<CohortFill>,
    #[serde(default)]
    transition_drain: Option<CohortTransitionDrainTelemetry>,
}

/// Latest complete read-only cohort state used by all four TUI screens.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct BackendCohortTelemetry {
    pub enabled_symbols: Vec<String>,
    pub asset_configs: Vec<CohortAssetConfig>,
    pub providers: Vec<CohortProvider>,
    pub strategy_evidence: Vec<CohortStrategyEvidence>,
    pub maximum_concurrent_positions: usize,
    pub config_source_path: Option<String>,
    pub prestart_backup: Option<CohortPrestartBackupEvidence>,
    pub runtime: Option<CohortRuntimeConfig>,
    pub routing_policy: Option<CohortRoutingPolicy>,
    pub account: Option<CohortAccount>,
    pub assets: Vec<CohortAssetSnapshot>,
    pub actions: Vec<CohortRoutingAction>,
    pub withheld: Vec<CohortWithheldIntent>,
    pub evaluations: Vec<CohortProviderEvaluation>,
    pub setup_coverage: Option<CohortSetupCoverage>,
    pub regime_history: Vec<CohortProviderEvaluation>,
    pub fills: Vec<CohortFill>,
    pub mark_history: BTreeMap<String, Vec<f64>>,
    pub candle_history: BTreeMap<String, Vec<CohortCandle>>,
    pub books: BTreeMap<String, CohortBookSnapshot>,
    pub operator_events: Vec<CohortOperatorEvent>,
    pub transition_drain: Option<CohortTransitionDrainTelemetry>,
    pub last_observed_at: Option<String>,
    pub heartbeat: Option<CohortHeartbeat>,
    pub runtime_fault_at: Option<String>,
    pub runtime_stopped_at: Option<String>,
}

/// Parse cohort-specific rows, failing if a cohort ledger is structurally invalid.
pub(crate) fn project_cohort(rows: &[&LedgerRow]) -> Result<BackendCohortTelemetry, String> {
    let Some(identity) = rows
        .iter()
        .find(|row| row.action == "configuration_identity")
    else {
        return Ok(BackendCohortTelemetry::default());
    };
    if identity.strategy_name.as_deref() != Some("multi_asset_bidirectional_cohort") {
        return Ok(BackendCohortTelemetry::default());
    }
    let identity = project_identity(identity)?;
    let candle_history = candle_history(rows, &identity.enabled_symbols)?;
    let books = crate::backend_cohort_book::project_books(rows, &identity.enabled_symbols)?;
    let mut cohort = BackendCohortTelemetry {
        enabled_symbols: identity.enabled_symbols,
        asset_configs: identity.asset_configs,
        providers: identity.providers,
        strategy_evidence: identity.strategy_evidence,
        maximum_concurrent_positions: identity.maximum_concurrent_positions,
        config_source_path: identity.config_source_path,
        prestart_backup: identity.prestart_backup,
        runtime: identity.runtime,
        routing_policy: identity.routing_policy,
        mark_history: mark_history(rows)?,
        candle_history,
        books,
        operator_events: crate::backend_cohort_operator::project_operator_events(rows)?,
        ..BackendCohortTelemetry::default()
    };
    apply_latest_snapshot(rows, &mut cohort)?;
    routing::apply_routing_history(rows, &mut cohort)?;
    cohort.last_observed_at = rows.last().map(|row| row.feed_ts.clone());
    cohort.heartbeat = crate::backend_cohort_health::project_heartbeat(rows);
    cohort.runtime_fault_at = crate::backend_cohort_health::project_fault(rows);
    cohort.runtime_stopped_at = crate::backend_cohort_health::project_stopped(rows);
    Ok(cohort)
}

fn apply_latest_snapshot(
    rows: &[&LedgerRow],
    cohort: &mut BackendCohortTelemetry,
) -> Result<(), String> {
    let Some(row) = rows
        .iter()
        .rev()
        .find(|row| row.action == "cohort_snapshot")
    else {
        return Ok(());
    };
    let mut payload: CohortSnapshotPayload = parse_payload(row)?;
    validate_snapshot(&cohort.enabled_symbols, &payload.assets)?;
    validate_account_balance_source(payload.account_balance_source.as_deref())?;
    if let Some(drain) = payload.transition_drain.as_ref() {
        crate::backend_cohort_operator::validate_transition_drain(
            drain,
            row.run_id.as_deref(),
            row.profile_fingerprint.as_deref(),
        )?;
    }
    for asset in &mut payload.assets {
        asset.reconcile_position_mark()?;
    }
    cohort.account = Some(CohortAccount {
        account_value_usd: payload.account_value_usd,
        withdrawable_usd: payload.withdrawable_usd,
        total_margin_used_usd: payload.total_margin_used_usd,
        total_notional_position_usd: payload.total_notional_position_usd,
        open_position_count: payload.open_position_count,
        account_balance_source: payload.account_balance_source,
    });
    cohort.assets = payload.assets;
    cohort.fills = payload.recent_fills;
    cohort.transition_drain = payload.transition_drain;
    Ok(())
}

fn validate_account_balance_source(source: Option<&str>) -> Result<(), String> {
    match source {
        None | Some("perp_clearinghouse_state" | "spot_clearinghouse_state") => Ok(()),
        Some(value) => Err(format!(
            "unsupported cohort account balance source: {value}"
        )),
    }
}

fn retain_tail<T>(values: &mut Vec<T>, maximum: usize) {
    if values.len() > maximum {
        values.drain(..values.len() - maximum);
    }
}

fn mark_history(rows: &[&LedgerRow]) -> Result<BTreeMap<String, Vec<f64>>, String> {
    let mut history: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    for row in rows.iter().filter(|row| row.action == "cohort_snapshot") {
        let payload: CohortSnapshotPayload = parse_payload(row)?;
        for asset in payload.assets {
            if let Some(mark) = asset.market_reference_price.or(asset.mark_price) {
                history.entry(asset.symbol).or_default().push(mark);
            }
        }
    }
    Ok(history)
}

fn parse_payload<T: DeserializeOwned>(row: &LedgerRow) -> Result<T, String> {
    let values = row.extra.clone().into_iter().collect();
    serde_json::from_value(Value::Object(values))
        .map_err(|error| format!("invalid {} payload: {error}", row.action))
}

fn parse_extra<T: DeserializeOwned>(row: &LedgerRow, key: &str) -> Result<T, String> {
    let value = row
        .extra
        .get(key)
        .cloned()
        .ok_or_else(|| format!("cohort identity is missing {key}"))?;
    serde_json::from_value(value).map_err(|error| format!("invalid cohort {key}: {error}"))
}
