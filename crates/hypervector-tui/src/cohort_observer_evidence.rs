//! Typed evidence records for the execution-incapable cohort observer.

use std::collections::BTreeMap;

use crate::backend_cohort_opportunity_capture::{
    CohortOneBlockerNearMisses, CohortOpportunityCapture,
};
use crate::backend_cohort_orderbook_opportunity::CohortProviderOrderbookOpportunity;
use crate::backend_cohort_repeatability::CohortRepeatabilityEvidence;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;

/// One provider/symbol row from the observer's causal research journal.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortObserverProviderEvidence {
    pub strategy_id: String,
    pub symbol: String,
    pub research_state: Option<String>,
    pub confidence: Option<String>,
    pub historical_cadence: Option<String>,
    pub historical_summary: Option<String>,
    pub evidence_source: Option<String>,
    pub directional_research: BTreeMap<String, CohortDirectionalResearchEvidence>,
    pub forward_assessment: Option<String>,
    pub execution_performance_scope: Option<String>,
    pub execution_performance: Option<CohortTradePerformanceSummary>,
    pub execution_performance_by_side: BTreeMap<String, CohortTradePerformanceSummary>,
    pub repeatability_evidence: Option<CohortRepeatabilityEvidence>,
    pub latest_side: Option<String>,
    pub readiness_fraction: Option<f64>,
    pub latest_reason: Option<String>,
    pub latest_blockers: Vec<String>,
    pub readiness_evaluations: usize,
    pub eligible_signals: usize,
    pub paths: BTreeMap<u16, CohortObserverPathEvidence>,
    pub eligible_paths: BTreeMap<u16, CohortObserverPathEvidence>,
    pub readiness_paths: BTreeMap<u16, CohortObserverPathEvidence>,
    pub one_blocker_near_misses: Option<CohortOneBlockerNearMisses>,
    pub orderbook_opportunity: Option<CohortProviderOrderbookOpportunity>,
}

/// One side-specific historical qualification with no execution authority.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortDirectionalResearchEvidence {
    pub side: String,
    pub research_state: String,
    pub confidence: String,
    pub cadence: String,
    pub summary: String,
    pub evidence_source: String,
}

/// Descriptive directional path statistics for one causal horizon.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortObserverPathEvidence {
    pub resolved: usize,
    pub independent: usize,
    pub censored: usize,
    pub missing_data: usize,
    pub mean_directional_return_bps: Option<f64>,
    pub positive_directional_rate: Option<f64>,
    pub opportunity_capture: Option<CohortOpportunityCapture>,
}
