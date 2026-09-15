//! Wire types for the live checkpoint audit envelope.

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort::CohortFill;
use crate::backend_cohort_allocation::AllocationChallengerRaw;
use crate::backend_cohort_asymmetric_forward::AsymmetricForwardRaw;
use crate::backend_cohort_checkpoint::{
    CoverageEvidence, ObserverSignalOutcomesEvidence, ReadinessEvidence,
};
use crate::backend_cohort_checkpoint_values::LearningEvidence;
use crate::backend_cohort_eligible_policy_forward::EligiblePolicyForwardRaw;
use crate::backend_cohort_execution_opportunity_matrix::ExecutionOpportunityMatrixRaw;
use crate::backend_cohort_friction_parity::FrictionParityEvidence;
use crate::backend_cohort_hulk_entry_quality::HulkEntryQualityRaw;
use crate::backend_cohort_live_audit::{LiveAuditHealthRaw, LiveAuditRunRaw, LiveAuditRuntimeRaw};
use crate::backend_cohort_maximum_hold::MaximumHoldEvidenceRaw;
use crate::backend_cohort_orderbook_opportunity::ObserverOrderbookOpportunityRaw;
use crate::backend_cohort_portfolio::CohortPortfolioEvidence;
use crate::backend_cohort_portfolio_archive::PortfolioArchiveRaw;
use crate::backend_cohort_regime_conflicts::RegimeConflictEvidenceRaw;
use crate::backend_cohort_risk_utilization::RiskUtilizationEvidenceRaw;
use crate::backend_cohort_side_composition::SideCompositionRaw;
use crate::backend_cohort_strategy_scorecard::ObserverStrategyScorecardEvidence;
use crate::backend_cohort_trade_reflections::{
    OpenTradeReflectionEvidence, TradeReflectionEvidence,
};

#[derive(Debug, Deserialize)]
pub(crate) struct LiveAuditEvidence {
    pub(crate) coverage: CoverageEvidence,
    pub(crate) readiness: ReadinessEvidence,
    #[serde(default)]
    pub(crate) routing: Option<LiveRoutingEvidence>,
    #[serde(default)]
    pub(crate) runtime: Option<LiveAuditRuntimeRaw>,
    #[serde(default)]
    pub(crate) health: Option<LiveAuditHealthRaw>,
    #[serde(default)]
    pub(crate) run: Option<LiveAuditRunRaw>,
    #[serde(default)]
    pub(crate) signal_outcomes: Option<ObserverSignalOutcomesEvidence>,
    #[serde(default)]
    pub(crate) orderbook_opportunity: Option<ObserverOrderbookOpportunityRaw>,
    #[serde(default)]
    pub(crate) regime_conflict_journal: Option<RegimeConflictEvidenceRaw>,
    #[serde(default)]
    pub(crate) maximum_hold_decisions: Option<MaximumHoldEvidenceRaw>,
    #[serde(default)]
    pub(crate) profit_lock_challenger: Option<Value>,
    #[serde(default)]
    pub(crate) strategy_scorecard: Option<ObserverStrategyScorecardEvidence>,
    #[serde(default)]
    pub(crate) portfolio: Option<CohortPortfolioEvidence>,
    #[serde(default)]
    pub(crate) portfolio_archive: Option<PortfolioArchiveRaw>,
    #[serde(default)]
    pub(crate) risk_utilization: Option<RiskUtilizationEvidenceRaw>,
    #[serde(default)]
    pub(crate) allocation_challenger: Option<AllocationChallengerRaw>,
    #[serde(default)]
    pub(crate) asymmetric_forward_observer: Option<AsymmetricForwardRaw>,
    #[serde(default)]
    pub(crate) side_composition: Option<SideCompositionRaw>,
    #[serde(default)]
    pub(crate) execution_opportunity_matrix: Option<ExecutionOpportunityMatrixRaw>,
    #[serde(default)]
    pub(crate) eligible_policy_forward: Option<EligiblePolicyForwardRaw>,
    #[serde(default)]
    pub(crate) hulk_entry_quality_challenger: Option<HulkEntryQualityRaw>,
    pub(crate) execution: ExecutionEvidence,
    #[serde(default)]
    pub(crate) trade_reflections: Option<TradeReflectionEvidence>,
    #[serde(default)]
    pub(crate) open_trade_reflections: Option<OpenTradeReflectionEvidence>,
    pub(crate) learning: LearningEvidence,
}

#[derive(Debug, Deserialize)]
pub(crate) struct LiveRoutingEvidence {
    pub(crate) actions: usize,
    pub(crate) strategy_intents: usize,
    #[serde(default)]
    pub(crate) entry_age_diagnostics:
        Option<crate::backend_cohort_entry_deadline::CohortEntryDeadlines>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ExecutionEvidence {
    #[serde(default)]
    pub(crate) scope: Option<String>,
    pub(crate) closed_trades: usize,
    #[serde(default)]
    pub(crate) open_lifecycles: Option<usize>,
    pub(crate) net_pnl_usd: f64,
    #[serde(default)]
    pub(crate) fill_details: Vec<CohortFill>,
    #[serde(default)]
    pub(crate) friction_parity: Option<FrictionParityEvidence>,
}
