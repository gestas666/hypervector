//! Strict read-only projection of the rolling cohort analysis checkpoint.
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeMap;

use crate::backend_cohort::CohortFill;
use crate::backend_cohort_allocation::{CohortAllocationChallenger, project_allocation_challenger};
use crate::backend_cohort_asymmetric_forward::{
    CohortAsymmetricForwardObserver, project_asymmetric_forward_observer,
};
use crate::backend_cohort_checkpoint_journal::provider_journal;
use crate::backend_cohort_checkpoint_live::LiveAuditEvidence;
use crate::backend_cohort_checkpoint_values::{analysis_mode, five_minute_path_counts};
use crate::backend_cohort_configuration::{
    CohortConfigurationGeneration, ConfigurationGenerationEvidenceRaw,
    project_configuration_generation,
};
use crate::backend_cohort_eligible_policy_forward::{
    CohortEligiblePolicyForward, project_eligible_policy_forward,
};
use crate::backend_cohort_execution_opportunity_matrix::{
    CohortExecutionOpportunityMatrix, project_execution_opportunity_matrix,
};
use crate::backend_cohort_friction_parity::{CohortFrictionParity, project_friction_parity};
use crate::backend_cohort_hulk_entry_quality::{
    CohortHulkEntryQuality, project_hulk_entry_quality,
};
pub use crate::backend_cohort_live_audit::CohortLiveAuditStatus;
use crate::backend_cohort_live_audit::project_live_audit_status;
use crate::backend_cohort_maximum_hold::{
    CohortMaximumHoldEvidence, project_maximum_hold_decisions,
};
use crate::backend_cohort_opportunity_capture::{
    ObserverOneBlockerNearMissesRaw, ObserverOpportunityCaptureRaw,
};
use crate::backend_cohort_portfolio::{CohortPortfolioEvidence, project_portfolio};
use crate::backend_cohort_portfolio_archive::{CohortPortfolioArchive, project_portfolio_archive};
use crate::backend_cohort_profit_lock::{CohortProfitLockEvidence, parse_profit_lock_evidence};
use crate::backend_cohort_regime_conflicts::{
    CohortRegimeConflictEvidence, project_regime_conflicts,
};
use crate::backend_cohort_risk_utilization::{CohortRiskUtilization, project_risk_utilization};
use crate::backend_cohort_side_composition::{CohortSideComposition, project_side_composition};
use crate::backend_cohort_strategy_scorecard::ObserverStrategyScorecardEvidence;
use crate::backend_cohort_trade_performance::CohortTradePerformance;
use crate::backend_cohort_trade_reflections::{
    CohortOpenTradeReflection, CohortTimerContextEvidence, CohortTradeReflection,
    project_open_trade_reflections, project_trade_reflections, provider_contract_outcome_count,
};
use crate::backend_cohort_venue_portfolio::project_venue_portfolio;
pub use crate::backend_cohort_venue_portfolio::{CohortValuedSpotAsset, CohortVenuePortfolio};
pub use crate::cohort_observer_evidence::{
    CohortObserverPathEvidence, CohortObserverProviderEvidence,
};
#[path = "backend_cohort_checkpoint_validation.rs"]
mod validation;
use validation::{validate_envelope, validate_live, validate_observer};
const LIVE_MODE: &str = "multi_asset_bidirectional_live_checkpoint";
const OBSERVER_MODE: &str = "multi_asset_bidirectional_observer_checkpoint";
/// Latest aggregate technical and statistical evidence from the Python sidecar.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortCheckpointTelemetry {
    pub configured: bool,
    pub available: bool,
    pub stale: bool,
    pub generated_at_utc: Option<String>,
    pub run_id: Option<String>,
    pub profile_id: Option<String>,
    pub profile_fingerprint: Option<String>,
    pub analysis_mode: Option<String>,
    pub configuration_generation: Option<CohortConfigurationGeneration>,
    pub lifecycle_state: Option<String>,
    pub cohort_heartbeat_status: Option<String>,
    pub asset_states: BTreeMap<String, String>,
    pub coverage_complete: Option<bool>,
    pub technical_gaps: Vec<String>,
    pub readiness_evaluations: Option<usize>,
    pub strategy_intents: Option<usize>,
    pub routing_actions: Option<usize>,
    pub live_audit_status: Option<CohortLiveAuditStatus>,
    pub forward_evaluations: Option<usize>,
    pub eligible_signals: Option<usize>,
    pub five_minute_paths_resolved: Option<usize>,
    pub five_minute_paths_independent: Option<usize>,
    pub forward_path_coverage_complete: Option<bool>,
    pub closed_trades: Option<usize>,
    pub net_pnl_usd: Option<f64>,
    pub venue_portfolio: Option<CohortVenuePortfolio>,
    pub venue_portfolio_issue: Option<String>,
    pub portfolio: Option<CohortPortfolioEvidence>,
    pub portfolio_archive: Option<CohortPortfolioArchive>,
    pub risk_utilization: Option<CohortRiskUtilization>,
    pub allocation_challenger: Option<CohortAllocationChallenger>,
    pub asymmetric_forward_observer: Option<CohortAsymmetricForwardObserver>,
    pub side_composition: Option<CohortSideComposition>,
    pub friction_parity: Option<CohortFrictionParity>,
    pub regime_conflicts: Option<CohortRegimeConflictEvidence>,
    pub maximum_hold_decisions: Option<CohortMaximumHoldEvidence>,
    pub profit_lock_challenger: Option<CohortProfitLockEvidence>,
    pub execution_opportunity_matrix: Option<CohortExecutionOpportunityMatrix>,
    pub eligible_policy_forward: Option<CohortEligiblePolicyForward>,
    pub hulk_entry_quality: Option<CohortHulkEntryQuality>,
    pub evidence_state: Option<String>,
    pub trade_reflection_context_complete: Option<bool>,
    pub timer_context_evidence: Option<CohortTimerContextEvidence>,
    pub trade_reflections: Vec<CohortTradeReflection>,
    pub all_time_trade_reflections: Vec<CohortTradeReflection>,
    pub trade_performance: Option<CohortTradePerformance>,
    pub fill_details: Vec<CohortFill>,
    pub open_trade_reflections: Vec<CohortOpenTradeReflection>,
    pub observer_provider_journal: Vec<CohortObserverProviderEvidence>,
    pub issue: Option<String>,
}

impl CohortCheckpointTelemetry {
    /// Return the complete user ledger, with legacy compatible-history fallback.
    pub fn user_trade_reflections(&self) -> &[CohortTradeReflection] {
        if self.all_time_trade_reflections.is_empty() {
            &self.trade_reflections
        } else {
            &self.all_time_trade_reflections
        }
    }

    /// Return the durable all-profile archive when the backend supplied it.
    pub fn all_time_performance(
        &self,
    ) -> Option<&crate::backend_cohort_trade_performance::CohortAllTimeTradePerformance> {
        let archive = self
            .portfolio_archive
            .as_ref()
            .map(|value| &value.performance);
        let reflected = self
            .trade_performance
            .as_ref()
            .and_then(|value| value.all_time_live.as_ref());
        match (archive, reflected) {
            (Some(archived), Some(value))
                if value.total.closed_trades > archived.total.closed_trades =>
            {
                Some(value)
            }
            (Some(archived), _) => Some(archived),
            (None, value) => value,
        }
    }
}
#[derive(Debug, Deserialize)]
struct CheckpointDocument {
    schema_version: u64,
    mode: String,
    generated_at_utc: String,
    #[serde(default)]
    venue_portfolio: Option<Value>,
    status: Option<UnavailableStatus>,
    configuration_generation: Option<ConfigurationGenerationEvidenceRaw>,
    lifecycle: Option<LifecycleEvidence>,
    observer: Option<ObserverEvidence>,
    audit: Option<Value>,
}
#[derive(Debug, Deserialize)]
struct UnavailableStatus {
    state: String,
    technical_issue: String,
}
#[derive(Debug, Deserialize)]
struct LifecycleEvidence {
    state: String,
    cohort_heartbeat_status: Option<String>,
    asset_states: BTreeMap<String, String>,
}
#[derive(Debug, Deserialize)]
struct ObserverEvidence {
    state: String,
    run_id: String,
    last_observed_at_utc: String,
}
#[derive(Debug, Deserialize)]
struct ObserverAuditEvidence {
    technical: ObserverTechnicalEvidence,
    runtime: ObserverRuntimeEvidence,
    readiness: ReadinessEvidence,
    signals: ObserverSignalEvidence,
    signal_outcomes: ObserverSignalOutcomesEvidence,
    #[serde(default)]
    strategy_scorecard: Option<ObserverStrategyScorecardEvidence>,
    learning: crate::backend_cohort_checkpoint_values::LearningEvidence,
}
#[derive(Debug, Deserialize)]
pub(crate) struct ObserverSignalOutcomesEvidence {
    pub(crate) evaluations: usize,
    pub(crate) eligible_evaluations: usize,
    coverage: ObserverPathCoverage,
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderPathEvidence>,
}
#[derive(Debug, Deserialize)]
struct ObserverPathCoverage {
    complete: bool,
}
#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderPathEvidence {
    #[serde(default)]
    pub(crate) evaluations: Option<usize>,
    #[serde(default)]
    pub(crate) eligible_evaluations: Option<usize>,
    pub(crate) horizons: BTreeMap<String, ObserverHorizonEvidence>,
    #[serde(default)]
    pub(crate) by_evidence_class: BTreeMap<String, ObserverEvidenceClassPaths>,
    #[serde(default)]
    pub(crate) one_blocker_near_misses: Option<ObserverOneBlockerNearMissesRaw>,
}
#[derive(Debug, Deserialize)]
pub(crate) struct ObserverEvidenceClassPaths {
    #[serde(default)]
    pub(crate) horizons: BTreeMap<String, ObserverHorizonEvidence>,
}
#[derive(Debug, Deserialize)]
pub(crate) struct ObserverHorizonEvidence {
    pub(crate) resolved: usize,
    pub(crate) non_overlapping_resolved: usize,
    #[serde(default)]
    pub(crate) censored: usize,
    #[serde(default)]
    pub(crate) missing_data: usize,
    #[serde(default)]
    pub(crate) mean_directional_close_return_bps: Option<f64>,
    #[serde(default)]
    pub(crate) positive_directional_rate: Option<f64>,
    #[serde(default)]
    pub(crate) opportunity_capture: Option<ObserverOpportunityCaptureRaw>,
    #[serde(default)]
    pub(crate) independent_opportunity_capture: Option<ObserverOpportunityCaptureRaw>,
}
#[derive(Debug, Deserialize)]
struct ObserverTechnicalEvidence {
    complete: bool,
    technical_gaps: Vec<String>,
}
#[derive(Debug, Deserialize)]
struct ObserverRuntimeEvidence {
    poll_cycles: usize,
}

#[derive(Debug, Deserialize)]
struct ObserverSignalEvidence {
    strategy_intents: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CoverageEvidence {
    complete: bool,
    technical_gaps: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ReadinessEvidence {
    pub(crate) evaluations: usize,
    #[serde(default)]
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderReadiness>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderReadiness {
    pub(crate) count: usize,
    pub(crate) eligible: usize,
    #[serde(default)]
    pub(crate) latest_fraction: Option<f64>,
    #[serde(default)]
    pub(crate) latest_side: Option<String>,
    #[serde(default)]
    pub(crate) latest_reason: Option<String>,
    #[serde(default)]
    pub(crate) latest_blockers: Vec<String>,
}

/// Parse one atomically published checkpoint without strategy inference.
pub fn parse_cohort_checkpoint(content: &str) -> Result<CohortCheckpointTelemetry, String> {
    let document: CheckpointDocument = serde_json::from_str(content)
        .map_err(|error| format!("invalid checkpoint JSON: {error}"))?;
    validate_envelope(&document)?;
    if let Some(status) = document.status {
        return parse_unavailable(
            document.generated_at_utc,
            status,
            analysis_mode(&document.mode),
        );
    }
    if document.mode == OBSERVER_MODE {
        return parse_observer(document);
    }
    parse_live(document)
}

fn parse_live(document: CheckpointDocument) -> Result<CohortCheckpointTelemetry, String> {
    let (venue_portfolio, venue_portfolio_issue) =
        project_venue_portfolio(document.venue_portfolio.clone())?;
    let configuration_generation =
        project_configuration_generation(document.configuration_generation)?;
    let lifecycle = document
        .lifecycle
        .ok_or_else(|| "ready checkpoint is missing lifecycle evidence".to_string())?;
    let audit: LiveAuditEvidence = serde_json::from_value(
        document
            .audit
            .ok_or_else(|| "ready checkpoint is missing audit evidence".to_string())?,
    )
    .map_err(|error| format!("invalid live checkpoint audit: {error}"))?;
    validate_live(&lifecycle, &audit)?;
    let backend_issue = match lifecycle.state.as_str() {
        "backend_heartbeat_stale" => {
            Some("execution backend heartbeat has not advanced for more than 60s".to_string())
        }
        "backend_runtime_fault" => {
            Some("execution backend reported a terminal runtime fault".to_string())
        }
        _ => None,
    };
    let backend_stale = backend_issue.is_some();
    let (run_id, profile_id, profile_fingerprint) =
        crate::backend_cohort_live_audit::project_live_run_identity(audit.run.as_ref())?;
    let live_audit_status = project_live_audit_status(audit.runtime, audit.health, audit.run)?;
    let scorecard_outcomes = provider_contract_outcome_count(audit.trade_reflections.as_ref())?
        .or(Some(audit.execution.closed_trades));
    let (resolved, independent, provider_journal) = match &audit.signal_outcomes {
        Some(outcomes) => {
            let (resolved, independent) = five_minute_path_counts(outcomes)?;
            let journal = provider_journal(
                &audit.readiness,
                outcomes,
                audit.orderbook_opportunity.as_ref(),
                audit.strategy_scorecard.as_ref(),
                scorecard_outcomes,
            )?;
            (Some(resolved), Some(independent), journal)
        }
        None => (None, None, Vec::new()),
    };
    let (
        reflection_complete,
        trade_reflections,
        all_time_trade_reflections,
        timer_context_evidence,
        trade_performance,
    ) = project_trade_reflections(audit.trade_reflections, audit.execution.closed_trades)?;
    let open_trade_reflections = project_open_trade_reflections(
        audit.open_trade_reflections,
        audit.execution.open_lifecycles,
    )?;
    let friction_parity = project_friction_parity(audit.execution.friction_parity.as_ref())?;
    let portfolio = project_portfolio(audit.portfolio)?;
    let portfolio_archive = project_portfolio_archive(audit.portfolio_archive)?;
    let risk_utilization = project_risk_utilization(audit.risk_utilization)?;
    let allocation_challenger =
        project_allocation_challenger(audit.allocation_challenger, risk_utilization.as_ref())?;
    let asymmetric_forward_observer =
        project_asymmetric_forward_observer(audit.asymmetric_forward_observer)?;
    let side_composition = project_side_composition(
        audit.side_composition,
        run_id.as_deref(),
        profile_id.as_deref(),
        profile_fingerprint.as_deref(),
    )?;
    let regime_conflicts = project_regime_conflicts(audit.regime_conflict_journal)?;
    let maximum_hold_decisions = project_maximum_hold_decisions(audit.maximum_hold_decisions)?;
    let profit_lock_challenger = parse_profit_lock_evidence(audit.profit_lock_challenger)?;
    let execution_opportunity_matrix =
        project_execution_opportunity_matrix(audit.execution_opportunity_matrix)?;
    let eligible_policy_forward = project_eligible_policy_forward(audit.eligible_policy_forward)?;
    let hulk_entry_quality = project_hulk_entry_quality(audit.hulk_entry_quality_challenger)?;
    Ok(CohortCheckpointTelemetry {
        configured: true,
        available: true,
        stale: backend_stale,
        generated_at_utc: Some(document.generated_at_utc),
        run_id,
        profile_id,
        profile_fingerprint,
        analysis_mode: Some("live_execution".into()),
        configuration_generation,
        lifecycle_state: Some(lifecycle.state),
        cohort_heartbeat_status: lifecycle.cohort_heartbeat_status,
        asset_states: lifecycle.asset_states,
        coverage_complete: Some(audit.coverage.complete),
        technical_gaps: audit.coverage.technical_gaps,
        readiness_evaluations: Some(audit.readiness.evaluations),
        strategy_intents: audit
            .routing
            .as_ref()
            .map(|routing| routing.strategy_intents),
        routing_actions: audit.routing.map(|routing| routing.actions),
        live_audit_status,
        forward_evaluations: audit
            .signal_outcomes
            .as_ref()
            .map(|outcomes| outcomes.evaluations),
        eligible_signals: audit
            .signal_outcomes
            .as_ref()
            .map(|outcomes| outcomes.eligible_evaluations),
        five_minute_paths_resolved: resolved,
        five_minute_paths_independent: independent,
        forward_path_coverage_complete: audit
            .signal_outcomes
            .as_ref()
            .map(|outcomes| outcomes.coverage.complete),
        closed_trades: Some(audit.execution.closed_trades),
        net_pnl_usd: Some(audit.execution.net_pnl_usd),
        venue_portfolio,
        venue_portfolio_issue,
        portfolio,
        portfolio_archive,
        risk_utilization,
        allocation_challenger,
        asymmetric_forward_observer,
        side_composition,
        friction_parity,
        regime_conflicts,
        maximum_hold_decisions,
        profit_lock_challenger,
        execution_opportunity_matrix,
        eligible_policy_forward,
        hulk_entry_quality,
        evidence_state: Some(audit.learning.evidence_state),
        trade_reflection_context_complete: reflection_complete,
        timer_context_evidence,
        trade_reflections,
        all_time_trade_reflections,
        trade_performance,
        fill_details: audit.execution.fill_details,
        open_trade_reflections,
        observer_provider_journal: provider_journal,
        issue: backend_issue,
        ..CohortCheckpointTelemetry::default()
    })
}

fn parse_observer(document: CheckpointDocument) -> Result<CohortCheckpointTelemetry, String> {
    let observer = document
        .observer
        .ok_or_else(|| "ready observer checkpoint is missing observer evidence".to_string())?;
    let audit: ObserverAuditEvidence = serde_json::from_value(
        document
            .audit
            .ok_or_else(|| "ready observer checkpoint is missing audit evidence".to_string())?,
    )
    .map_err(|error| format!("invalid observer checkpoint audit: {error}"))?;
    validate_observer(&observer, &audit)?;
    let (resolved, independent) = five_minute_path_counts(&audit.signal_outcomes)?;
    let provider_journal = provider_journal(
        &audit.readiness,
        &audit.signal_outcomes,
        None,
        audit.strategy_scorecard.as_ref(),
        None,
    )?;
    Ok(CohortCheckpointTelemetry {
        configured: true,
        available: true,
        generated_at_utc: Some(document.generated_at_utc),
        run_id: Some(observer.run_id),
        analysis_mode: Some("forward_observer".into()),
        lifecycle_state: Some(observer.state),
        coverage_complete: Some(audit.technical.complete),
        technical_gaps: audit.technical.technical_gaps,
        readiness_evaluations: Some(audit.readiness.evaluations),
        strategy_intents: Some(audit.signals.strategy_intents),
        forward_evaluations: Some(audit.signal_outcomes.evaluations),
        eligible_signals: Some(audit.signal_outcomes.eligible_evaluations),
        five_minute_paths_resolved: Some(resolved),
        five_minute_paths_independent: Some(independent),
        forward_path_coverage_complete: Some(audit.signal_outcomes.coverage.complete),
        evidence_state: Some(audit.learning.evidence_state),
        observer_provider_journal: provider_journal,
        ..CohortCheckpointTelemetry::default()
    })
}

fn parse_unavailable(
    generated_at_utc: String,
    status: UnavailableStatus,
    analysis_mode: String,
) -> Result<CohortCheckpointTelemetry, String> {
    if status.state != "unavailable" || status.technical_issue.trim().is_empty() {
        return Err("invalid unavailable checkpoint status".into());
    }
    Ok(CohortCheckpointTelemetry {
        configured: true,
        generated_at_utc: Some(generated_at_utc),
        analysis_mode: Some(analysis_mode),
        issue: Some(status.technical_issue),
        ..CohortCheckpointTelemetry::default()
    })
}
