//! Public read-only projection of one open cohort lifecycle.

use crate::backend_cohort_exit_plan::CohortOpenExitPlan;
use crate::backend_cohort_extension_path::CohortOpenExtensionPath;
use crate::backend_cohort_ignored_provider_exit::CohortIgnoredProviderExit;
use crate::backend_cohort_open_path::CohortOpenPath;
use crate::backend_cohort_open_post_soft_trail::CohortOpenPostSoftTrail;
use crate::backend_cohort_open_profit_lock::CohortOpenProfitLock;
use crate::backend_cohort_open_profit_protection::CohortOpenProfitProtection;
use crate::backend_cohort_regime_opposition::CohortRegimeOppositionEpisode;
use crate::backend_cohort_trade_reflections::CohortTradeRegimeContext;

/// Entry-to-current regime drift for one still-open live lifecycle.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenTradeReflection {
    pub lifecycle_id: String,
    pub source_run_id: String,
    pub symbol: String,
    pub strategy_id: String,
    pub side: String,
    pub holding_time_ms: u64,
    pub entry_size: Option<f64>,
    pub protective_stop_oid: Option<u64>,
    pub protective_stop_price: Option<f64>,
    /// Set only when the ledger acknowledged a venue raise replacing the checkpoint's stop.
    pub protective_stop_raise: Option<CohortOpenStopRaise>,
    pub profit_protection: Option<CohortOpenProfitProtection>,
    pub target_order_oid: Option<u64>,
    pub target_order_price: Option<f64>,
    pub target_directional_distance_bps: Option<f64>,
    pub exit_plan: CohortOpenExitPlan,
    pub path_since_entry: CohortOpenPath,
    pub path_since_soft_deadline: Option<CohortOpenExtensionPath>,
    pub post_soft_trail_challenger: Option<CohortOpenPostSoftTrail>,
    pub open_profit_lock_challenger: Option<CohortOpenProfitLock>,
    pub ignored_provider_exit_observer: Option<CohortIgnoredProviderExit>,
    pub entry_signal: CohortTradeRegimeContext,
    pub entry_canonical: CohortTradeRegimeContext,
    pub entry_structure_support_score: Option<f64>,
    pub entry_structure_stance: String,
    pub current_signal: CohortTradeRegimeContext,
    pub current_canonical: CohortTradeRegimeContext,
    pub signal_provider_changed: Option<bool>,
    pub canonical_regime_changed: Option<bool>,
    pub structure_support_score: Option<f64>,
    pub structure_stance: String,
    pub component_alignment_score: Option<f64>,
    pub component_stance: String,
    pub movement_strength: Option<f64>,
    pub maximum_hold_context: String,
    pub regime_opposition: Option<CohortRegimeOppositionEpisode>,
    pub mark_price: f64,
    pub active_lifecycle_marked_net_pnl_usd: f64,
}

/// The checkpoint-attributed stop that an acknowledged venue raise replaced.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortOpenStopRaise {
    pub previous_oid: u64,
    pub previous_trigger_price: f64,
    /// The backend found its owned stop already resting at the raise target.
    pub already_at_target: bool,
}
