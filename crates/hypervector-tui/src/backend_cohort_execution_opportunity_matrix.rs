//! Strict projection of executable, report-only missed-opportunity evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use crate::backend_cohort_candidate_portfolio::project_candidate_portfolio_journal;
pub use crate::backend_cohort_forward_challenger::CohortForwardOneBlockerChallenger;
use crate::backend_cohort_forward_challenger::{
    CohortForwardExecution, CohortForwardPayoffGeometry, ForwardExecutionRaw,
    ForwardOneBlockerChallengerRaw, ForwardPayoffGeometryRaw, project_forward_execution_contract,
};
use crate::backend_cohort_forward_entry_context::{
    project_forward_context_15m, project_forward_entry_context,
};
use crate::backend_cohort_forward_validation::{
    approximately_equal, optional_fraction_valid, summary_valid, validate_forward_challenger,
};
pub use crate::backend_cohort_opportunity_provenance::CohortOpportunityMatrixProvenance;
use crate::backend_cohort_opportunity_provenance::{
    CohortOpportunityMatrixProvenanceRaw, project_opportunity_matrix_provenance,
};
use crate::backend_cohort_supplemental_challengers::project_supplemental_forward_challengers;

/// Read-only matrix of separately evaluated exact-one-blocker hypotheses.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortExecutionOpportunityMatrix {
    pub provenance: Option<CohortOpportunityMatrixProvenance>,
    pub hypotheses: usize,
    pub comparisons: usize,
    pub scope: Option<CohortExecutionOpportunityScope>,
    pub results: Vec<CohortExecutionOpportunityComparison>,
    pub forward_challenger: Option<CohortForwardOneBlockerChallenger>,
    pub supplemental_forward_challengers: Vec<CohortForwardOneBlockerChallenger>,
}
impl CohortExecutionOpportunityMatrix {
    /// Return the most observed non-OPI-gated row without ranking profitability.
    pub fn broadest_all_cohort(&self) -> Option<&CohortExecutionOpportunityComparison> {
        self.results
            .iter()
            .filter(|row| row.opi_cohort == "all")
            .max_by_key(|row| row.resolved)
    }
}
/// Auditable split between observed and executable blocker hypotheses.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortExecutionOpportunityScope {
    pub observed_hypotheses: usize,
    pub executable_hypotheses: usize,
    pub excluded_non_executable_hypotheses: usize,
}
/// One non-additive executable comparison for a provider, symbol, and blocker.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortExecutionOpportunityComparison {
    pub strategy_id: String,
    pub symbol: String,
    pub blocker: String,
    pub opi_cohort: String,
    pub resolved: usize,
    pub wins: usize,
    pub losses: usize,
    pub total_net_return_bps: f64,
    pub mean_net_return_bps: Option<f64>,
    pub profit_factor: Option<f64>,
    pub largest_abs_contribution_fraction: Option<f64>,
    pub stop_proxy_crosses: usize,
    pub long_resolved: usize,
    pub short_resolved: usize,
}
#[derive(Debug, Deserialize)]
pub(crate) struct ExecutionOpportunityMatrixRaw {
    schema_version: u64,
    mode: String,
    contract: ExecutionOpportunityMatrixContract,
    hypotheses: usize,
    comparisons: usize,
    #[serde(default)]
    scope: Option<ExecutionOpportunityScopeRaw>,
    #[serde(default)]
    checkpoint_provenance: Option<CohortOpportunityMatrixProvenanceRaw>,
    results: Vec<ExecutionOpportunityComparisonRaw>,
    #[serde(default)]
    forward_challenger: Option<ForwardOneBlockerChallengerRaw>,
    #[serde(default)]
    supplemental_forward_challengers: Vec<ForwardOneBlockerChallengerRaw>,
    limitations: Vec<String>,
}
#[derive(Debug, Deserialize)]
struct ExecutionOpportunityScopeRaw {
    observed_hypotheses: usize,
    executable_hypotheses: usize,
    excluded_non_executable_hypotheses: Vec<OpportunityHypothesisIdentityRaw>,
}
#[derive(Debug, Deserialize)]
struct OpportunityHypothesisIdentityRaw {
    strategy_id: String,
    symbol: String,
    blocker: String,
}
#[derive(Debug, Deserialize)]
struct ExecutionOpportunityMatrixContract {
    report_only: bool,
    execution_authority: String,
    live_strategy_changed: bool,
    portfolio_pnl_claimed: bool,
    thresholds_fitted: bool,
    horizon_minutes: usize,
    opi_cohorts: Vec<String>,
    comparisons_are_not_additive: bool,
}

#[derive(Debug, Deserialize)]
struct ExecutionOpportunityComparisonRaw {
    strategy_id: String,
    symbol: String,
    blocker: String,
    opi_cohort: String,
    resolved: usize,
    wins: usize,
    losses: usize,
    total_net_return_bps: f64,
    mean_net_return_bps: Option<f64>,
    profit_factor: Option<f64>,
    largest_abs_contribution_fraction: Option<f64>,
    stop_proxy_crosses: usize,
    long: SideResultRaw,
    short: SideResultRaw,
}

#[derive(Debug, Deserialize)]
struct SideResultRaw {
    resolved: usize,
    wins: usize,
    losses: usize,
    total_net_return_bps: f64,
    mean_net_return_bps: Option<f64>,
    profit_factor: Option<f64>,
    stop_proxy_crosses: usize,
}

pub(crate) fn project_execution_opportunity_matrix(
    raw: Option<ExecutionOpportunityMatrixRaw>,
) -> Result<Option<CohortExecutionOpportunityMatrix>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_envelope(&raw)?;
    let scope = project_hypothesis_scope(raw.scope, raw.hypotheses, &raw.results)?;
    let provenance = project_opportunity_matrix_provenance(raw.checkpoint_provenance)?;
    let forward_challenger = project_forward_challenger(raw.forward_challenger)?;
    let supplemental_forward_challengers = project_supplemental_forward_challengers(
        &forward_challenger,
        raw.supplemental_forward_challengers,
    )?;
    let results = raw
        .results
        .into_iter()
        .map(project_comparison)
        .collect::<Result<Vec<_>, _>>()?;
    validate_hypothesis_groups(raw.hypotheses, &results)?;
    Ok(Some(CohortExecutionOpportunityMatrix {
        provenance,
        hypotheses: raw.hypotheses,
        comparisons: raw.comparisons,
        scope,
        results,
        forward_challenger,
        supplemental_forward_challengers,
    }))
}

fn project_hypothesis_scope(
    raw: Option<ExecutionOpportunityScopeRaw>,
    hypotheses: usize,
    results: &[ExecutionOpportunityComparisonRaw],
) -> Result<Option<CohortExecutionOpportunityScope>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    let excluded = raw
        .excluded_non_executable_hypotheses
        .iter()
        .map(|row| {
            (
                row.strategy_id.as_str(),
                row.symbol.as_str(),
                row.blocker.as_str(),
            )
        })
        .collect::<BTreeSet<_>>();
    let executable = results
        .iter()
        .map(|row| {
            (
                row.strategy_id.as_str(),
                row.symbol.as_str(),
                row.blocker.as_str(),
            )
        })
        .collect::<BTreeSet<_>>();
    let excluded_count = raw.excluded_non_executable_hypotheses.len();
    let invalid_identity = raw.excluded_non_executable_hypotheses.iter().any(|row| {
        row.strategy_id.trim().is_empty()
            || row.symbol.trim().is_empty()
            || row.blocker.trim().is_empty()
    });
    if raw.executable_hypotheses != hypotheses
        || raw.observed_hypotheses < hypotheses
        || excluded_count != raw.observed_hypotheses - hypotheses
        || excluded.len() != excluded_count
        || invalid_identity
        || excluded
            .iter()
            .any(|identity| executable.contains(identity))
    {
        return Err("execution opportunity hypothesis scope is inconsistent".into());
    }
    Ok(Some(CohortExecutionOpportunityScope {
        observed_hypotheses: raw.observed_hypotheses,
        executable_hypotheses: raw.executable_hypotheses,
        excluded_non_executable_hypotheses: excluded_count,
    }))
}

pub(crate) fn project_forward_challenger(
    raw: Option<ForwardOneBlockerChallengerRaw>,
) -> Result<Option<CohortForwardOneBlockerChallenger>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_forward_challenger(&raw)?;
    let execution_contract = project_forward_execution_contract(&raw);
    let portfolio_journal = project_candidate_portfolio_journal(raw.portfolio_journal)?;
    let payoff_geometry = raw.payoff_geometry.map(project_payoff_geometry);
    let entry_context_summary = project_forward_entry_context(
        raw.entry_context_summary,
        raw.summary.resolved,
        raw.summary.total_net_return_bps,
    )?;
    let context_15m_summary = project_forward_context_15m(
        raw.context_15m_summary,
        raw.summary.resolved,
        raw.summary.total_net_return_bps,
    )?;
    let latest_execution = raw
        .latest_executions
        .into_iter()
        .last()
        .map(project_forward_execution);
    Ok(Some(CohortForwardOneBlockerChallenger {
        state: raw.state,
        generated_at_utc: raw.generated_at_utc,
        execution_contract,
        target_proxy_bps: raw.contract.execution.target_proxy_bps,
        payoff_geometry,
        exact_candidates: raw.coverage.exact_candidates,
        selected_non_overlapping: raw.coverage.selected_non_overlapping,
        resolved: raw.summary.resolved,
        wins: raw.summary.wins,
        losses: raw.summary.losses,
        total_net_return_bps: raw.summary.total_net_return_bps,
        profit_factor: raw.summary.profit_factor,
        largest_abs_contribution_fraction: raw.summary.largest_abs_contribution_fraction,
        stop_proxy_crosses: raw.summary.stop_proxy_crosses,
        long_resolved: raw.summary.long_resolved,
        short_resolved: raw.summary.short_resolved,
        entry_context_summary,
        context_15m_summary,
        latest_execution,
        portfolio_journal,
    }))
}

fn project_payoff_geometry(raw: ForwardPayoffGeometryRaw) -> CohortForwardPayoffGeometry {
    CohortForwardPayoffGeometry {
        estimated_round_trip_fee_bps: raw.estimated_round_trip_fee_bps,
        estimated_target_net_bps: raw.estimated_target_net_bps,
        estimated_stop_net_bps: raw.estimated_stop_net_bps,
        break_even_target_rate_pct: raw.break_even_target_rate_pct,
        fixed_horizon_changes_realized_distribution: raw
            .fixed_horizon_changes_realized_distribution,
    }
}

fn project_forward_execution(raw: ForwardExecutionRaw) -> CohortForwardExecution {
    CohortForwardExecution {
        source_run_id: raw.source_run_id,
        side: raw.side,
        entry_time_ms: raw.entry_time_ms,
        exit_time_ms: raw.exit_time_ms,
        entry_price: raw.entry_price,
        exit_price: raw.exit_price,
        exit_reason: raw.exit_reason,
        gross_return_bps: raw.gross_return_bps,
        fee_bps: raw.fee_bps,
        funding_bps: raw.funding_bps,
        net_return_bps: raw.net_return_bps,
        mfe_bps: raw.mfe_bps,
        mae_bps: raw.mae_bps,
        crossed_stop_proxy: raw.crossed_stop_proxy,
    }
}

fn validate_envelope(raw: &ExecutionOpportunityMatrixRaw) -> Result<(), String> {
    let expected_cohorts = BTreeSet::from(["aligned", "all", "opposed"]);
    let cohorts = raw
        .contract
        .opi_cohorts
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if raw.schema_version != 1
        || raw.mode != "cohort_execution_opportunity_matrix"
        || raw.comparisons != raw.results.len()
        || raw.comparisons != raw.hypotheses.saturating_mul(3)
        || raw.limitations.is_empty()
        || raw.limitations.iter().any(|value| value.trim().is_empty())
        || cohorts != expected_cohorts
        || raw.contract.opi_cohorts.len() != 3
        || raw.contract.horizon_minutes != 60
    {
        return Err("execution opportunity matrix envelope is inconsistent".into());
    }
    validate_contract(&raw.contract)
}

fn validate_contract(contract: &ExecutionOpportunityMatrixContract) -> Result<(), String> {
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.live_strategy_changed
        || contract.portfolio_pnl_claimed
        || contract.thresholds_fitted
        || !contract.comparisons_are_not_additive
    {
        return Err("execution opportunity matrix contract exceeded report-only authority".into());
    }
    Ok(())
}

fn project_comparison(
    raw: ExecutionOpportunityComparisonRaw,
) -> Result<CohortExecutionOpportunityComparison, String> {
    validate_comparison(&raw)?;
    Ok(CohortExecutionOpportunityComparison {
        strategy_id: raw.strategy_id,
        symbol: raw.symbol,
        blocker: raw.blocker,
        opi_cohort: raw.opi_cohort,
        resolved: raw.resolved,
        wins: raw.wins,
        losses: raw.losses,
        total_net_return_bps: raw.total_net_return_bps,
        mean_net_return_bps: raw.mean_net_return_bps,
        profit_factor: raw.profit_factor,
        largest_abs_contribution_fraction: raw.largest_abs_contribution_fraction,
        stop_proxy_crosses: raw.stop_proxy_crosses,
        long_resolved: raw.long.resolved,
        short_resolved: raw.short.resolved,
    })
}

fn validate_comparison(raw: &ExecutionOpportunityComparisonRaw) -> Result<(), String> {
    let identity_valid = !raw.strategy_id.trim().is_empty()
        && !raw.symbol.trim().is_empty()
        && !raw.blocker.trim().is_empty()
        && matches!(raw.opi_cohort.as_str(), "aligned" | "opposed" | "all");
    if !identity_valid
        || !summary_valid(
            raw.resolved,
            raw.wins,
            raw.losses,
            raw.total_net_return_bps,
            raw.mean_net_return_bps,
            raw.profit_factor,
            raw.stop_proxy_crosses,
        )
        || !side_valid(&raw.long)
        || !side_valid(&raw.short)
        || raw.long.resolved + raw.short.resolved != raw.resolved
        || raw.long.wins + raw.short.wins != raw.wins
        || raw.long.losses + raw.short.losses != raw.losses
        || raw.long.stop_proxy_crosses + raw.short.stop_proxy_crosses != raw.stop_proxy_crosses
        || !approximately_equal(
            raw.long.total_net_return_bps + raw.short.total_net_return_bps,
            raw.total_net_return_bps,
        )
        || !optional_fraction_valid(
            raw.largest_abs_contribution_fraction,
            raw.resolved,
            raw.wins,
            raw.losses,
        )
    {
        return Err("execution opportunity comparison is inconsistent".into());
    }
    Ok(())
}

fn side_valid(side: &SideResultRaw) -> bool {
    summary_valid(
        side.resolved,
        side.wins,
        side.losses,
        side.total_net_return_bps,
        side.mean_net_return_bps,
        side.profit_factor,
        side.stop_proxy_crosses,
    )
}

fn validate_hypothesis_groups(
    hypotheses: usize,
    results: &[CohortExecutionOpportunityComparison],
) -> Result<(), String> {
    let mut groups: BTreeMap<(&str, &str, &str), BTreeSet<&str>> = BTreeMap::new();
    for row in results {
        groups
            .entry((&row.strategy_id, &row.symbol, &row.blocker))
            .or_default()
            .insert(&row.opi_cohort);
    }
    let expected = BTreeSet::from(["aligned", "all", "opposed"]);
    if groups.len() != hypotheses || groups.values().any(|cohorts| cohorts != &expected) {
        return Err("execution opportunity matrix hypothesis groups are inconsistent".into());
    }
    Ok(())
}
