//! Strict wire types for the frozen report-only forward challenger.

use serde::Deserialize;

use crate::backend_cohort_forward_entry_context::{
    CohortForwardContext15mSummary, CohortForwardEntryContextSummary, ForwardContext15mRaw,
    ForwardEntryContextRaw,
};

/// Latest resolved causal path in the frozen forward journal.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardExecution {
    pub source_run_id: String,
    pub side: String,
    pub entry_time_ms: u64,
    pub exit_time_ms: u64,
    pub entry_price: f64,
    pub exit_price: f64,
    pub exit_reason: String,
    pub gross_return_bps: f64,
    pub fee_bps: f64,
    pub funding_bps: f64,
    pub net_return_bps: f64,
    pub mfe_bps: f64,
    pub mae_bps: f64,
    pub crossed_stop_proxy: bool,
}

/// Fresh post-cutoff status for the single frozen executable challenger.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardOneBlockerChallenger {
    pub state: String,
    pub generated_at_utc: String,
    pub execution_contract: CohortForwardExecutionContract,
    pub target_proxy_bps: Option<f64>,
    pub payoff_geometry: Option<CohortForwardPayoffGeometry>,
    pub exact_candidates: usize,
    pub selected_non_overlapping: usize,
    pub resolved: usize,
    pub wins: usize,
    pub losses: usize,
    pub total_net_return_bps: f64,
    pub profit_factor: Option<f64>,
    pub largest_abs_contribution_fraction: Option<f64>,
    pub stop_proxy_crosses: usize,
    pub long_resolved: usize,
    pub short_resolved: usize,
    pub entry_context_summary: Option<CohortForwardEntryContextSummary>,
    pub context_15m_summary: Option<CohortForwardContext15mSummary>,
    pub latest_execution: Option<CohortForwardExecution>,
    pub portfolio_journal: Option<CohortCandidatePortfolioJournal>,
}

/// Frozen execution terms retained after checkpoint validation for operator inspection.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardExecutionContract {
    pub strategy_id: String,
    pub symbol: String,
    pub blocker: String,
    pub opi_cohort: String,
    pub horizon_minutes: usize,
    pub maximum_context_age_ms: Option<u64>,
    pub maximum_entry_delay_ms: Option<u64>,
    pub maximum_exit_delay_ms: Option<u64>,
    pub minimum_entry_spacing_minutes: usize,
    pub notional_usd: f64,
    pub taker_fee_rate: f64,
    pub stop_proxy_bps: f64,
    pub target_proxy_bps: Option<f64>,
    pub cutoff_time_ms: u64,
    pub cutoff_utc: String,
    pub minimum_available_time_ms: u64,
    pub execution_authority: String,
}

/// Fee-adjusted binary target/stop benchmark for a target-first challenger.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardPayoffGeometry {
    pub estimated_round_trip_fee_bps: f64,
    pub estimated_target_net_bps: f64,
    pub estimated_stop_net_bps: f64,
    pub break_even_target_rate_pct: Option<f64>,
    pub fixed_horizon_changes_realized_distribution: bool,
}

/// Portfolio compatibility totals for the staged flat-entry candidate.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortCandidatePortfolioJournal {
    pub source_strategy_id: String,
    pub candidate_strategy_id: String,
    pub symbol: String,
    pub attempts: usize,
    pub deployable: usize,
    pub deployable_resolved: Option<usize>,
    pub deployable_wins: Option<usize>,
    pub deployable_losses: Option<usize>,
    pub deployable_total_net_return_bps: Option<f64>,
    pub deployable_profit_factor: Option<f64>,
    pub deployable_largest_abs_contribution_fraction: Option<f64>,
    pub existing_symbol_position: usize,
    pub portfolio_capacity: usize,
    pub same_cycle_symbol_action: usize,
    pub portfolio_state_unavailable: usize,
    pub resolved: usize,
    pub pending: usize,
    pub latest_attempt: Option<CohortCandidatePortfolioAttempt>,
}

/// Latest causal portfolio classification for one selected candidate attempt.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortCandidatePortfolioAttempt {
    pub source_run_id: String,
    pub side: String,
    pub decision_time_ms: u64,
    pub classification: String,
    pub open_position_count: Option<usize>,
    pub available_position_slots: Option<usize>,
    pub outcome_status: String,
    pub net_return_bps: Option<f64>,
    pub current_estimated_net_return_bps: Option<f64>,
    pub mfe_bps: Option<f64>,
    pub mae_bps: Option<f64>,
    pub remaining_ms: Option<u64>,
    pub current_exit_top_level_capacity: Option<bool>,
    pub primary_regime: Option<String>,
    pub state_1m: Option<String>,
    pub state_5m: Option<String>,
    pub context_15m: Option<String>,
    pub structural_direction: Option<String>,
    pub breakout_volume_ratio: Option<f64>,
    pub current_bbwp_percentile: Option<f64>,
    pub regime_strength: Option<f64>,
    pub same_cycle_action_count: usize,
    pub same_cycle_withheld_count: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardOneBlockerChallengerRaw {
    pub(crate) schema_version: u64,
    pub(crate) mode: String,
    pub(crate) state: String,
    pub(crate) generated_at_utc: String,
    pub(crate) contract: ForwardChallengerContract,
    pub(crate) coverage: ForwardChallengerCoverage,
    pub(crate) summary: ForwardChallengerSummary,
    #[serde(default)]
    pub(crate) entry_context_summary: Option<ForwardEntryContextRaw>,
    #[serde(default)]
    pub(crate) context_15m_summary: Option<ForwardContext15mRaw>,
    #[serde(default)]
    pub(crate) payoff_geometry: Option<ForwardPayoffGeometryRaw>,
    pub(crate) latest_executions: Vec<ForwardExecutionRaw>,
    #[serde(default)]
    pub(crate) portfolio_journal: Option<CandidatePortfolioJournalRaw>,
    pub(crate) falsifiers: Vec<String>,
    pub(crate) limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardPayoffGeometryRaw {
    pub(crate) scope: String,
    pub(crate) execution_authority: String,
    pub(crate) performance_gate: bool,
    pub(crate) target_proxy_bps: f64,
    pub(crate) stop_proxy_bps: f64,
    pub(crate) estimated_round_trip_fee_bps: f64,
    pub(crate) estimated_target_net_bps: f64,
    pub(crate) estimated_stop_net_bps: f64,
    pub(crate) break_even_target_rate_pct: Option<f64>,
    pub(crate) fixed_horizon_changes_realized_distribution: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidatePortfolioJournalRaw {
    pub(crate) schema_version: u64,
    pub(crate) mode: String,
    pub(crate) state: String,
    pub(crate) contract: CandidatePortfolioContractRaw,
    pub(crate) summary: CandidatePortfolioSummaryRaw,
    pub(crate) latest_attempts: Vec<CandidatePortfolioAttemptRaw>,
    pub(crate) limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidatePortfolioContractRaw {
    pub(crate) report_only: bool,
    pub(crate) execution_authority: String,
    pub(crate) source_strategy_id: String,
    pub(crate) candidate_strategy_id: String,
    pub(crate) symbol: String,
    pub(crate) position_policy: String,
    pub(crate) maximum_positions: usize,
    pub(crate) portfolio_pnl_claimed: bool,
    pub(crate) simulated_outcomes_are_non_additive: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidatePortfolioSummaryRaw {
    pub(crate) attempts: usize,
    pub(crate) deployable: usize,
    #[serde(default)]
    pub(crate) deployable_resolved: Option<usize>,
    #[serde(default)]
    pub(crate) deployable_wins: Option<usize>,
    #[serde(default)]
    pub(crate) deployable_losses: Option<usize>,
    #[serde(default)]
    pub(crate) deployable_total_net_return_bps: Option<f64>,
    #[serde(default)]
    pub(crate) deployable_profit_factor: Option<f64>,
    #[serde(default)]
    pub(crate) deployable_largest_abs_contribution_fraction: Option<f64>,
    pub(crate) existing_symbol_position: usize,
    pub(crate) portfolio_capacity: usize,
    pub(crate) same_cycle_symbol_action: usize,
    pub(crate) portfolio_state_unavailable: usize,
    pub(crate) resolved: usize,
    pub(crate) pending: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidatePortfolioAttemptRaw {
    pub(crate) source_run_id: String,
    pub(crate) side: String,
    pub(crate) decision_time_ms: u64,
    pub(crate) portfolio_classification: String,
    pub(crate) open_position_count: Option<usize>,
    pub(crate) available_position_slots: Option<usize>,
    pub(crate) symbol_state: Option<String>,
    pub(crate) symbol_position_side: Option<String>,
    pub(crate) same_cycle_symbol_actions: Vec<CandidateRouteRaw>,
    pub(crate) same_cycle_symbol_withheld: Vec<CandidateRouteRaw>,
    pub(crate) outcome_status: String,
    pub(crate) net_return_bps: Option<f64>,
    pub(crate) simulated_net_pnl_usd: Option<f64>,
    #[serde(default)]
    pub(crate) current_estimated_net_return_bps: Option<f64>,
    #[serde(default)]
    pub(crate) mfe_bps: Option<f64>,
    #[serde(default)]
    pub(crate) mae_bps: Option<f64>,
    #[serde(default)]
    pub(crate) remaining_ms: Option<u64>,
    #[serde(default)]
    pub(crate) current_exit_top_level_capacity: Option<bool>,
    #[serde(default)]
    pub(crate) entry_features: Option<CandidateEntryFeaturesRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidateEntryFeaturesRaw {
    #[serde(default)]
    pub(crate) primary_regime: Option<String>,
    #[serde(default)]
    pub(crate) state_1m: Option<String>,
    #[serde(default)]
    pub(crate) state_5m: Option<String>,
    #[serde(default)]
    pub(crate) context_15m: Option<String>,
    #[serde(default)]
    pub(crate) structural_direction: Option<String>,
    #[serde(default)]
    pub(crate) breakout_volume_ratio: Option<f64>,
    #[serde(default)]
    pub(crate) current_bbwp_percentile: Option<f64>,
    #[serde(default)]
    pub(crate) regime_strength: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CandidateRouteRaw {
    pub(crate) strategy_id: String,
    pub(crate) reason: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardChallengerContract {
    pub(crate) report_only: bool,
    pub(crate) execution_authority: String,
    pub(crate) live_strategy_changed: bool,
    pub(crate) automatic_promotion: bool,
    pub(crate) portfolio_pnl_claimed: bool,
    pub(crate) direction_scope: Vec<String>,
    pub(crate) cutoff_time_ms: u64,
    pub(crate) cutoff_utc: String,
    pub(crate) execution: ForwardExecutionContract,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardExecutionContract {
    pub(crate) strategy_id: String,
    pub(crate) symbol: String,
    pub(crate) blocker: String,
    pub(crate) horizon_minutes: usize,
    #[serde(default)]
    pub(crate) maximum_context_age_ms: Option<u64>,
    #[serde(default)]
    pub(crate) maximum_entry_delay_ms: Option<u64>,
    #[serde(default)]
    pub(crate) maximum_exit_delay_ms: Option<u64>,
    pub(crate) minimum_entry_spacing_minutes: usize,
    pub(crate) notional_usd: f64,
    pub(crate) taker_fee_rate: f64,
    pub(crate) stop_proxy_bps: f64,
    #[serde(default)]
    pub(crate) target_proxy_bps: Option<f64>,
    pub(crate) opi_cohort: String,
    pub(crate) minimum_available_time_ms: u64,
    pub(crate) execution_authority: String,
}

pub(crate) fn project_forward_execution_contract(
    raw: &ForwardOneBlockerChallengerRaw,
) -> CohortForwardExecutionContract {
    let execution = &raw.contract.execution;
    CohortForwardExecutionContract {
        strategy_id: execution.strategy_id.clone(),
        symbol: execution.symbol.clone(),
        blocker: execution.blocker.clone(),
        opi_cohort: execution.opi_cohort.clone(),
        horizon_minutes: execution.horizon_minutes,
        maximum_context_age_ms: execution.maximum_context_age_ms,
        maximum_entry_delay_ms: execution.maximum_entry_delay_ms,
        maximum_exit_delay_ms: execution.maximum_exit_delay_ms,
        minimum_entry_spacing_minutes: execution.minimum_entry_spacing_minutes,
        notional_usd: execution.notional_usd,
        taker_fee_rate: execution.taker_fee_rate,
        stop_proxy_bps: execution.stop_proxy_bps,
        target_proxy_bps: execution.target_proxy_bps,
        cutoff_time_ms: raw.contract.cutoff_time_ms,
        cutoff_utc: raw.contract.cutoff_utc.clone(),
        minimum_available_time_ms: execution.minimum_available_time_ms,
        execution_authority: execution.execution_authority.clone(),
    }
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardChallengerCoverage {
    pub(crate) exact_candidates: usize,
    pub(crate) selected_non_overlapping: usize,
    pub(crate) resolved_executions: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardChallengerSummary {
    pub(crate) resolved: usize,
    pub(crate) wins: usize,
    pub(crate) losses: usize,
    pub(crate) total_net_return_bps: f64,
    pub(crate) mean_net_return_bps: Option<f64>,
    pub(crate) profit_factor: Option<f64>,
    pub(crate) largest_abs_contribution_fraction: Option<f64>,
    pub(crate) stop_proxy_crosses: usize,
    pub(crate) long_resolved: usize,
    pub(crate) short_resolved: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardExecutionRaw {
    pub(crate) source_run_id: String,
    pub(crate) side: String,
    pub(crate) available_time_ms: u64,
    pub(crate) entry_time_ms: u64,
    pub(crate) exit_time_ms: u64,
    pub(crate) entry_price: f64,
    pub(crate) exit_price: f64,
    pub(crate) exit_reason: String,
    pub(crate) gross_return_bps: f64,
    pub(crate) fee_bps: f64,
    pub(crate) funding_bps: f64,
    pub(crate) net_return_bps: f64,
    pub(crate) mfe_bps: f64,
    pub(crate) mae_bps: f64,
    pub(crate) crossed_stop_proxy: bool,
}
