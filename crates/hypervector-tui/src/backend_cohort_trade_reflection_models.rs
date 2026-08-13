//! Public read-only models for closed lifecycle reflection evidence.

use std::collections::BTreeMap;

use crate::backend_cohort_closed_path::CohortTradeExitPath;
use crate::backend_cohort_entry_followthrough::CohortTradeEntryFollowthroughPath;
use crate::backend_cohort_hold_capture::CohortCompletedHoldCapture;
use crate::backend_cohort_ignored_provider_exit::CohortClosedIgnoredProviderExit;
use crate::backend_cohort_regime_opposition::CohortRegimeOppositionEpisode;

/// Point-in-time regime context retained for one lifecycle boundary.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradeRegimeContext {
    pub status: String,
    pub primary_regime: Option<String>,
    pub state_1m: Option<String>,
    pub state_5m: Option<String>,
    pub context_15m: Option<String>,
    pub confidence: Option<f64>,
    pub breakout_side: Option<String>,
    pub structural_direction: Option<String>,
    pub breakout_side_relation: Option<String>,
}

/// Report-only regime reflection for one closed live lifecycle.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradeReflection {
    pub lifecycle_id: String,
    pub source_run_id: String,
    pub source_profile_fingerprint: Option<String>,
    pub symbol: String,
    pub strategy_id: String,
    pub exit_controller_strategy_id: String,
    pub cross_provider_exit: bool,
    pub side: String,
    pub exit_reason: Option<String>,
    pub net_pnl_usd: f64,
    pub entry_price: Option<f64>,
    pub exit_price: Option<f64>,
    pub entry_venue_timestamp_ms: Option<u64>,
    pub exit_venue_timestamp_ms: Option<u64>,
    pub protective_stop_oid: Option<u64>,
    pub protective_stop_price: Option<f64>,
    pub holding_time_ms: Option<u64>,
    pub fees_usd: Option<f64>,
    pub funding_usd: Option<f64>,
    pub entry_margin_used_usd: Option<f64>,
    pub leverage: Option<f64>,
    pub price_return_pct: Option<f64>,
    pub net_return_on_margin_pct: Option<f64>,
    pub entry_signal: CohortTradeRegimeContext,
    pub entry_canonical: CohortTradeRegimeContext,
    pub entry_structure_support_score: Option<f64>,
    pub entry_structure_stance: String,
    pub entry_component_alignment_score: Option<f64>,
    pub entry_component_stance: String,
    pub entry_movement_strength: Option<f64>,
    pub entry_maximum_hold_context: String,
    pub exit_signal: CohortTradeRegimeContext,
    pub exit_canonical: CohortTradeRegimeContext,
    pub exit_controller: CohortTradeRegimeContext,
    pub exit_structure_support_score: Option<f64>,
    pub exit_structure_stance: String,
    pub exit_component_alignment_score: Option<f64>,
    pub exit_component_stance: String,
    pub exit_movement_strength: Option<f64>,
    pub exit_maximum_hold_context: String,
    pub regime_opposition: Option<CohortRegimeOppositionEpisode>,
    pub entry_followthrough_paths: BTreeMap<u16, CohortTradeEntryFollowthroughPath>,
    pub completed_hold_capture: Option<CohortCompletedHoldCapture>,
    pub ignored_provider_exit_outcome: Option<CohortClosedIgnoredProviderExit>,
    pub post_exit_paths: BTreeMap<u16, CohortTradeExitPath>,
}
