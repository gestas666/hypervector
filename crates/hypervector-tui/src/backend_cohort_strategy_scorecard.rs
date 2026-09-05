//! Validation for report-only cohort strategy scorecard evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use crate::backend_cohort_repeatability::{
    CohortRepeatabilityEvidence, RawRepeatabilityEvidence, project_repeatability,
};
use crate::backend_cohort_strategy_evidence::valid_research_confidence;
use crate::backend_cohort_trade_performance::{
    CohortTradePerformanceSummary, RawTradePerformanceSummary, project_summary, validate_aggregate,
};

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverStrategyScorecardEvidence {
    contract: ObserverStrategyScorecardContract,
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderScorecardEvidence>,
}

#[derive(Debug, Deserialize)]
struct ObserverStrategyScorecardContract {
    report_only: bool,
    performance_gate: bool,
    balance_gate: bool,
    #[serde(default)]
    trade_count_gate: bool,
    automatic_pause: bool,
    automatic_retuning: bool,
    execution_authority: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderScorecardEvidence {
    strategy_id: String,
    symbol: String,
    pub(crate) research_state: String,
    pub(crate) confidence: String,
    pub(crate) historical_cadence: String,
    pub(crate) historical_summary: String,
    pub(crate) evidence_source: String,
    #[serde(default)]
    pub(crate) directional_research: BTreeMap<String, ObserverDirectionalResearchEvidence>,
    pub(crate) forward_assessment: String,
    strategy_edge_identifiable: bool,
    execution_outcomes_identifiable: bool,
    #[serde(default)]
    execution_performance_scope: Option<String>,
    #[serde(default)]
    execution_performance: Option<RawTradePerformanceSummary>,
    #[serde(default)]
    execution_performance_by_side: BTreeMap<String, RawTradePerformanceSummary>,
    #[serde(default)]
    repeatability_evidence: Option<RawRepeatabilityEvidence>,
    performance_gate: bool,
    execution_effect: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverDirectionalResearchEvidence {
    pub(crate) side: String,
    pub(crate) research_state: String,
    pub(crate) confidence: String,
    pub(crate) cadence: String,
    pub(crate) summary: String,
    pub(crate) evidence_source: String,
    execution_effect: String,
}

pub(crate) fn validate_strategy_scorecard(
    scorecard: &ObserverStrategyScorecardEvidence,
    expected_keys: &BTreeSet<String>,
) -> Result<(), String> {
    validate_contract(&scorecard.contract)?;
    let actual_keys = scorecard
        .by_provider_symbol
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();
    if actual_keys != *expected_keys {
        return Err("observer strategy scorecard coverage must match provider journal".into());
    }
    for (key, record) in &scorecard.by_provider_symbol {
        validate_record(key, record)?;
    }
    Ok(())
}

fn validate_contract(value: &ObserverStrategyScorecardContract) -> Result<(), String> {
    if !value.report_only
        || value.performance_gate
        || value.balance_gate
        || value.trade_count_gate
        || value.automatic_pause
        || value.automatic_retuning
        || value.execution_authority != "none"
    {
        return Err("observer strategy scorecard violates report-only contract".into());
    }
    Ok(())
}

fn validate_record(key: &str, value: &ObserverProviderScorecardEvidence) -> Result<(), String> {
    let (strategy_id, symbol) = provider_identity(key)?;
    let labels = [
        value.research_state.as_str(),
        value.historical_cadence.as_str(),
        value.historical_summary.as_str(),
        value.evidence_source.as_str(),
        value.forward_assessment.as_str(),
    ];
    if strategy_id != value.strategy_id
        || symbol != value.symbol
        || labels.iter().any(|label| label.trim().is_empty())
        || !valid_research_confidence(&value.confidence)
        || value.strategy_edge_identifiable
        || value.performance_gate
        || value.execution_effect != "report_only"
    {
        return Err("observer strategy scorecard provider record is invalid".into());
    }
    project_execution_performance(value)?;
    project_execution_performance_scope(value)?;
    project_execution_performance_by_side(value)?;
    project_repeatability_evidence(value)?;
    for (side, evidence) in &value.directional_research {
        validate_directional_record(side, evidence)?;
    }
    Ok(())
}

pub(crate) fn project_execution_performance_scope(
    value: &ObserverProviderScorecardEvidence,
) -> Result<Option<String>, String> {
    match (
        value.execution_outcomes_identifiable,
        value.execution_performance_scope.as_deref(),
    ) {
        (false, None) => Ok(None),
        (true, Some(scope))
            if matches!(
                scope,
                "compatible_profile_history" | "provider_execution_contract_history"
            ) =>
        {
            Ok(Some(scope.to_string()))
        }
        _ => Err("scorecard execution performance scope is invalid".into()),
    }
}

pub(crate) fn project_repeatability_evidence(
    value: &ObserverProviderScorecardEvidence,
) -> Result<Option<CohortRepeatabilityEvidence>, String> {
    let performance = project_execution_performance(value)?;
    project_repeatability(
        value.repeatability_evidence.as_ref(),
        performance.as_ref(),
        &value.strategy_id,
        &value.symbol,
    )
}

pub(crate) fn project_execution_performance_by_side(
    value: &ObserverProviderScorecardEvidence,
) -> Result<BTreeMap<String, CohortTradePerformanceSummary>, String> {
    if value.execution_performance_by_side.is_empty() {
        return Ok(BTreeMap::new());
    }
    if !value
        .execution_performance_by_side
        .keys()
        .all(|side| matches!(side.as_str(), "long" | "short"))
    {
        return Err("scorecard execution sides must be long or short".into());
    }
    let total = project_execution_performance(value)?
        .ok_or_else(|| "scorecard side execution outcomes require a pair total".to_string())?;
    let sides = value
        .execution_performance_by_side
        .iter()
        .map(|(side, raw)| Ok((side.clone(), project_summary(raw)?)))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    if sides.values().any(|summary| summary.closed_trades == 0) {
        return Err("scorecard side execution summary must contain trades".into());
    }
    validate_aggregate(&total, &sides)
        .map_err(|_| "scorecard side execution outcomes do not sum to pair total".to_string())?;
    Ok(sides)
}

pub(crate) fn project_execution_performance(
    value: &ObserverProviderScorecardEvidence,
) -> Result<Option<CohortTradePerformanceSummary>, String> {
    match (
        value.execution_outcomes_identifiable,
        value.execution_performance.as_ref(),
    ) {
        (false, None) => Ok(None),
        (true, Some(raw)) => {
            let projected = project_summary(raw)?;
            if projected.closed_trades == 0 {
                return Err("scorecard execution outcome summary must contain trades".into());
            }
            Ok(Some(projected))
        }
        _ => Err("scorecard execution outcome identity and summary disagree".into()),
    }
}

pub(crate) fn execution_outcome_count(
    scorecard: &ObserverStrategyScorecardEvidence,
) -> Result<usize, String> {
    scorecard
        .by_provider_symbol
        .values()
        .map(|record| {
            Ok(project_execution_performance(record)?.map_or(0, |value| value.closed_trades))
        })
        .sum()
}

fn validate_directional_record(
    side: &str,
    value: &ObserverDirectionalResearchEvidence,
) -> Result<(), String> {
    let labels = [
        value.research_state.as_str(),
        value.cadence.as_str(),
        value.summary.as_str(),
        value.evidence_source.as_str(),
    ];
    if !matches!(side, "long" | "short")
        || value.side != side
        || labels.iter().any(|label| label.trim().is_empty())
        || !valid_research_confidence(&value.confidence)
        || value.execution_effect != "report_only"
    {
        return Err("observer directional research record is invalid".into());
    }
    Ok(())
}

fn provider_identity(value: &str) -> Result<(&str, &str), String> {
    let (strategy, symbol) = value
        .split_once('|')
        .ok_or_else(|| "observer scorecard key must be strategy|symbol".to_string())?;
    if strategy.is_empty() || symbol.is_empty() || symbol.contains('|') {
        return Err("observer scorecard key must be strategy|symbol".into());
    }
    Ok((strategy, symbol))
}
