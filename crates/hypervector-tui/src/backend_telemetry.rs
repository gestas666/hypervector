//! Read-only projection of the authoritative Python paper/shadow ledger.

#[path = "backend_cohort_window.rs"]
mod backend_cohort_window;
#[path = "backend_telemetry_jsonl.rs"]
mod backend_telemetry_jsonl;
#[path = "backend_telemetry_portfolio.rs"]
mod backend_telemetry_portfolio;
#[path = "backend_telemetry_projection.rs"]
mod backend_telemetry_projection;
#[path = "backend_telemetry_snapshot_fields.rs"]
mod backend_telemetry_snapshot_fields;
#[path = "backend_telemetry_trade_records.rs"]
mod backend_telemetry_trade_records;
#[path = "backend_telemetry_trades.rs"]
mod backend_telemetry_trades;

use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use thiserror::Error;

use crate::backend_apex_mm::BackendApexMMTelemetry;
use crate::backend_cohort::BackendCohortTelemetry;
use crate::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use crate::backend_growth_preflight::GrowthPreflightTelemetry;
use crate::backend_hip3_roster::Hip3RosterTelemetry;
use crate::backend_hulk_smash::BackendHulkTelemetry;
use crate::backend_hype_l2_observer::HypeL2ObserverTelemetry;
use crate::backend_market::BackendBookTelemetry;
use crate::backend_observer::SourceLongOutcomeTelemetry;
use crate::backend_pine_stack::BackendPineTelemetry;
use crate::model::{
    ActivePosition, LivePaperStats, PaperTradeRecord, RegimeSnapshot, SourceRegimeDiagnostics,
};

pub use crate::backend_source::BackendTelemetrySource;

/// Health of the TUI's read-only connection to the backend ledger.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendConnectionState {
    Connected,
    Stale,
    Disconnected,
    Error,
}

/// Latest backend-confirmed state projected for display.
#[derive(Debug, Clone)]
pub struct BackendTelemetrySnapshot {
    pub connection: BackendConnectionState,
    pub status_message: String,
    pub run_id: Option<String>,
    pub export_id: Option<String>,
    pub data_root: Option<String>,
    pub symbol: Option<String>,
    pub profile_id: Option<String>,
    pub profile_fingerprint: Option<String>,
    pub capital_source: Option<String>,
    pub portfolio_purpose: Option<String>,
    pub backend_ledger_path: Option<String>,
    pub strategy_name: Option<String>,
    pub execution_mode: Option<String>,
    pub metalabel_mode: Option<String>,
    pub metalabel_policy: Value,
    pub metalabel_bundle_id: Option<String>,
    pub latest_metalabel_p: Option<f64>,
    pub latest_conviction_source: Option<String>,
    pub strategy_params: Value,
    pub exits: Value,
    pub risk: Value,
    pub execution_policy: Value,
    pub position_policy: Value,
    pub regime_policy: Value,
    pub observer_policies: Value,
    pub costs: Value,
    pub runtime: Value,
    pub orderbook_archive: Value,
    pub apex_mm: BackendApexMMTelemetry,
    pub hulk_smash: BackendHulkTelemetry,
    pub hip3_roster: Hip3RosterTelemetry,
    pub hype_l2_observer: HypeL2ObserverTelemetry,
    pub growth_preflight: GrowthPreflightTelemetry,
    pub pine_stack: BackendPineTelemetry,
    pub cohort: BackendCohortTelemetry,
    pub cohort_checkpoint: CohortCheckpointTelemetry,
    pub latest_regime: Option<String>,
    pub latest_regime_feed_ts: Option<String>,
    pub latest_regime_reason: Option<String>,
    pub latest_regime_confidence: Option<f64>,
    pub latest_regime_strength_score: Option<f64>,
    pub latest_regime_score_source: Option<String>,
    pub source_follow_signal_range_bps: Option<f64>,
    pub structural_direction: Option<String>,
    pub entry_direction: Option<String>,
    pub entry_allowed: Option<bool>,
    pub regime_admitted: Option<bool>,
    pub latest_decision_action: Option<String>,
    pub source_long_observer: Option<Value>,
    pub source_long_observer_signal_time: Option<String>,
    pub source_long_forward: Option<SourceLongOutcomeTelemetry>,
    pub wallet_configured: Option<bool>,
    pub signing_key_configured: Option<bool>,
    pub live_enabled: Option<bool>,
    pub live_armed: Option<bool>,
    pub live_state: Option<String>,
    pub execution_authority: Option<String>,
    pub protective_stop_oid: Option<u64>,
    pub protective_stop_status: Option<String>,
    pub protective_stop_price: Option<f64>,
    pub target_order_oid: Option<u64>,
    pub target_order_status: Option<String>,
    pub target_order_price: Option<f64>,
    pub latest_fault: Option<String>,
    pub compression_ready: Option<bool>,
    pub bbwp_compression_threshold: Option<f64>,
    pub ema_gap_bps_signed: Option<f64>,
    pub rsi_ema: Option<f64>,
    pub rsi_cross_direction: Option<String>,
    pub tactical_breakout_direction: Option<String>,
    pub breakout_volume_ratio: Option<f64>,
    pub prior_range_high: Option<f64>,
    pub prior_range_low: Option<f64>,
    pub pending_entry_direction: Option<String>,
    pub pending_maker_limit_price: Option<f64>,
    pub active_target_prices: Vec<f64>,
    pub entry_retry_state: Option<String>,
    pub entry_cooldown_active: Option<bool>,
    pub funding_rate_hourly: Option<f64>,
    pub regime_history: Vec<String>,
    pub regime_snapshots: Vec<RegimeSnapshot>,
    pub book: Option<BackendBookTelemetry>,
    pub trades: Vec<PaperTradeRecord>,
    pub stats: LivePaperStats,
    pub active_position: ActivePosition,
    pub equity_history: Vec<f64>,
}

macro_rules! empty_backend_snapshot {
    ($state:expr, $message:expr) => {
        BackendTelemetrySnapshot {
            connection: $state,
            status_message: $message.into(),
            run_id: None,
            export_id: None,
            data_root: None,
            symbol: None,
            profile_id: None,
            profile_fingerprint: None,
            capital_source: None,
            portfolio_purpose: None,
            backend_ledger_path: None,
            strategy_name: None,
            execution_mode: None,
            metalabel_mode: None,
            metalabel_policy: Value::Null,
            metalabel_bundle_id: None,
            latest_metalabel_p: None,
            latest_conviction_source: None,
            strategy_params: Value::Null,
            exits: Value::Null,
            risk: Value::Null,
            execution_policy: Value::Null,
            position_policy: Value::Null,
            regime_policy: Value::Null,
            observer_policies: Value::Null,
            costs: Value::Null,
            runtime: Value::Null,
            orderbook_archive: Value::Null,
            apex_mm: BackendApexMMTelemetry::default(),
            hulk_smash: BackendHulkTelemetry::default(),
            hip3_roster: Hip3RosterTelemetry::default(),
            hype_l2_observer: HypeL2ObserverTelemetry::default(),
            growth_preflight: GrowthPreflightTelemetry::default(),
            pine_stack: BackendPineTelemetry::default(),
            cohort: BackendCohortTelemetry::default(),
            cohort_checkpoint: CohortCheckpointTelemetry::default(),
            latest_regime: None,
            latest_regime_feed_ts: None,
            latest_regime_reason: None,
            latest_regime_confidence: None,
            latest_regime_strength_score: None,
            latest_regime_score_source: None,
            source_follow_signal_range_bps: None,
            structural_direction: None,
            entry_direction: None,
            entry_allowed: None,
            regime_admitted: None,
            latest_decision_action: None,
            source_long_observer: None,
            source_long_observer_signal_time: None,
            source_long_forward: None,
            wallet_configured: None,
            signing_key_configured: None,
            live_enabled: None,
            live_armed: None,
            live_state: None,
            execution_authority: None,
            protective_stop_oid: None,
            protective_stop_status: None,
            protective_stop_price: None,
            target_order_oid: None,
            target_order_status: None,
            target_order_price: None,
            latest_fault: None,
            compression_ready: None,
            bbwp_compression_threshold: None,
            ema_gap_bps_signed: None,
            rsi_ema: None,
            rsi_cross_direction: None,
            tactical_breakout_direction: None,
            breakout_volume_ratio: None,
            prior_range_high: None,
            prior_range_low: None,
            pending_entry_direction: None,
            pending_maker_limit_price: None,
            active_target_prices: Vec::new(),
            entry_retry_state: None,
            entry_cooldown_active: None,
            funding_rate_hourly: None,
            regime_history: Vec::new(),
            regime_snapshots: Vec::new(),
            book: None,
            trades: Vec::new(),
            stats: backend_telemetry_portfolio::empty_stats(),
            active_position: ActivePosition::flat(),
            equity_history: Vec::new(),
        }
    };
}

impl BackendTelemetrySnapshot {
    /// Report whether the backend is the Apex execution-measurement market maker.
    pub fn is_apex_mm(&self) -> bool {
        self.strategy_name.as_deref() == Some("apex_regime_mm_v2")
    }

    /// Report whether the backend uses the pinned five-minute source classifier.
    pub fn is_source_follow(&self) -> bool {
        self.regime_policy.get("engine").and_then(Value::as_str)
            == Some("pinned_hypertrader_source_follow_v1")
    }

    /// Report whether the backend is the rebuilt Hulk scored-signal candidate.
    pub fn is_hulk_smash(&self) -> bool {
        self.strategy_name
            .as_deref()
            .is_some_and(|name| name.starts_with("hulk_"))
            || self.regime_policy.get("engine").and_then(Value::as_str)
                == Some("hulk_smash_completed_bar_score_v3")
    }

    /// Report whether the backend is the four-Pine ETH 30m forward observer.
    pub fn is_pine_stack(&self) -> bool {
        self.strategy_name
            .as_deref()
            .is_some_and(|name| name.starts_with("pine_stack_"))
            || self.regime_policy.get("engine").and_then(Value::as_str)
                == Some("four_pine_completed_30m_observer_v1")
    }

    /// Report whether this is the shared bidirectional multi-asset backend.
    pub fn is_multi_asset_cohort(&self) -> bool {
        self.strategy_name.as_deref() == Some("multi_asset_bidirectional_cohort")
            || !self.cohort.enabled_symbols.is_empty()
    }

    /// Report whether the source-follow backend may execute both position sides.
    pub fn source_follow_is_bidirectional(&self) -> bool {
        self.is_source_follow()
            && self.regime_policy.get("side").and_then(Value::as_str) == Some("bidirectional")
    }

    /// Construct an empty snapshot that explicitly reports disconnection.
    pub fn disconnected(message: impl Into<String>) -> Self {
        Self::empty(BackendConnectionState::Disconnected, message)
    }

    pub(crate) fn error(message: impl Into<String>) -> Self {
        Self::empty(BackendConnectionState::Error, message)
    }

    fn empty(state: BackendConnectionState, message: impl Into<String>) -> Self {
        empty_backend_snapshot!(state, message)
    }
}

/// A structural error that prevents trustworthy ledger projection.
#[derive(Debug, Error)]
pub enum BackendTelemetryError {
    #[error("invalid backend ledger JSON at line {line}: {source}")]
    InvalidJson {
        line: usize,
        #[source]
        source: serde_json::Error,
    },
    #[error("invalid source regime diagnostics at line {line}: {reason}")]
    InvalidSourceDiagnostics { line: usize, reason: String },
    #[error("invalid multi-asset cohort telemetry: {reason}")]
    InvalidCohort { reason: String },
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct LedgerRow {
    #[serde(default)]
    pub(crate) feed_ts: String,
    #[serde(default)]
    pub(crate) action: String,
    #[serde(default)]
    skipped: bool,
    pub(crate) run_id: Option<String>,
    export_id: Option<String>,
    data_root: Option<String>,
    profile_id: Option<String>,
    pub(crate) profile_fingerprint: Option<String>,
    capital_source: Option<String>,
    portfolio_purpose: Option<String>,
    backend_ledger_path: Option<String>,
    pub(crate) strategy_name: Option<String>,
    execution_mode: Option<String>,
    metalabel_mode: Option<String>,
    metalabel_policy: Option<Value>,
    metalabel_bundle_id: Option<String>,
    conviction_source: Option<String>,
    metalabel_p: Option<f64>,
    symbol: Option<String>,
    wallet_configured: Option<bool>,
    signing_key_configured: Option<bool>,
    live_enabled: Option<bool>,
    live_armed: Option<bool>,
    pub(crate) fill_px: Option<f64>,
    fill_qty: Option<f64>,
    qty: Option<f64>,
    leverage: Option<f64>,
    position_qty: Option<f64>,
    position_avg_px: Option<f64>,
    liquidation_price: Option<f64>,
    equity: Option<f64>,
    init_cash: Option<f64>,
    realized_pnl: Option<f64>,
    unrealized_pnl: Option<f64>,
    pub(crate) fee_usd: Option<f64>,
    pub(crate) funding_payment_usd: Option<f64>,
    pub(crate) primary_regime: Option<String>,
    pub(crate) regime_diagnostics: Option<SourceRegimeDiagnostics>,
    strategy_params: Option<Value>,
    exits: Option<Value>,
    risk: Option<Value>,
    execution: Option<Value>,
    pub(crate) position_policy: Option<Value>,
    regime_policy: Option<Value>,
    observer_policies: Option<Value>,
    costs: Option<Value>,
    pub(crate) runtime: Option<Value>,
    orderbook_archive: Option<Value>,
    exit_reason: Option<String>,
    pub(crate) mark_px: Option<f64>,
    #[serde(flatten)]
    pub(crate) extra: HashMap<String, Value>,
}

/// Parse JSONL and project only the most recent identified backend run.
pub fn parse_backend_telemetry(
    content: &str,
) -> Result<BackendTelemetrySnapshot, BackendTelemetryError> {
    parse_backend_telemetry_retained(content).map(|(snapshot, _retained)| snapshot)
}

pub(crate) fn parse_backend_telemetry_retained(
    content: &str,
) -> Result<(BackendTelemetrySnapshot, String), BackendTelemetryError> {
    let bounded = backend_cohort_window::compact_latest_cohort(content)?;
    let retained = bounded.unwrap_or_else(|| content.to_owned());
    let rows = backend_telemetry_jsonl::parse_rows(&retained)?;
    let Some(run_id) = rows.iter().rev().find_map(|row| row.run_id.clone()) else {
        return Ok((
            BackendTelemetrySnapshot::disconnected("ledger has no run identity"),
            retained,
        ));
    };
    let run_rows: Vec<&LedgerRow> = rows
        .iter()
        .filter(|row| row.run_id.as_deref() == Some(run_id.as_str()))
        .collect();
    let snapshot = backend_telemetry_projection::build_snapshot(run_id, &run_rows)?;
    Ok((snapshot, retained))
}
