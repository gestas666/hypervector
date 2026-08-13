//! Strict read-only maximum-hold lifecycle decision projection.

use std::collections::{BTreeMap, HashSet};

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort_maximum_hold_extensions::{
    CohortMaximumHoldExtensionEvidence, MaximumHoldExtensionEvidenceRaw,
    project_maximum_hold_extension_outcomes,
};

#[derive(Debug, Clone, PartialEq)]
pub struct CohortMaximumHoldEvidence {
    pub observed: usize,
    pub extended: usize,
    pub exited: usize,
    pub provider_symbols: usize,
    pub latest_decisions: Vec<CohortMaximumHoldDecision>,
    pub extension_outcomes: Option<CohortMaximumHoldExtensionEvidence>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortMaximumHoldDecision {
    pub decision_id: String,
    pub lifecycle_id: String,
    pub symbol: String,
    pub strategy_id: String,
    pub side: String,
    pub decision_time_ms: u64,
    pub opened_at_ms: u64,
    pub elapsed_ms: u64,
    pub soft_deadline_timestamp_ms: u64,
    pub hard_deadline_timestamp_ms: Option<u64>,
    pub outcome: String,
    pub exit_reason: Option<String>,
    pub structure_alignment_score: Option<f64>,
    pub structure_alignment_threshold: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct MaximumHoldEvidenceRaw {
    contract: MaximumHoldContract,
    summary: MaximumHoldSummary,
    by_provider_symbol: BTreeMap<String, MaximumHoldProviderSummary>,
    latest_decisions: Vec<MaximumHoldDecisionRaw>,
    #[serde(default)]
    extension_outcomes: Option<MaximumHoldExtensionEvidenceRaw>,
}

#[derive(Debug, Deserialize)]
struct MaximumHoldContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct MaximumHoldSummary {
    observed: usize,
    extended: usize,
    exited: usize,
    provider_symbols: usize,
}

#[derive(Debug, Deserialize)]
struct MaximumHoldProviderSummary {
    observed: usize,
    extended: usize,
    exited: usize,
}

#[derive(Debug, Deserialize)]
struct MaximumHoldDecisionRaw {
    decision_id: String,
    lifecycle_id: String,
    symbol: String,
    strategy_id: String,
    side: String,
    decision_time_ms: u64,
    opened_at_ms: u64,
    elapsed_ms: u64,
    soft_deadline_timestamp_ms: u64,
    hard_deadline_timestamp_ms: Option<u64>,
    outcome: String,
    exit_reason: Option<String>,
    structure_alignment_score: Option<f64>,
    structure_alignment_threshold: f64,
    provider_evaluation: Option<Value>,
    canonical_evaluation: Option<Value>,
}

pub(crate) fn project_maximum_hold_decisions(
    raw: Option<MaximumHoldEvidenceRaw>,
) -> Result<Option<CohortMaximumHoldEvidence>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_contract(&raw.contract)?;
    validate_summary(&raw.summary, &raw.by_provider_symbol)?;
    let decisions = validate_decisions(raw.latest_decisions, raw.summary.observed)?;
    let extension_outcomes = project_maximum_hold_extension_outcomes(raw.extension_outcomes)?;
    Ok(Some(CohortMaximumHoldEvidence {
        observed: raw.summary.observed,
        extended: raw.summary.extended,
        exited: raw.summary.exited,
        provider_symbols: raw.summary.provider_symbols,
        latest_decisions: decisions,
        extension_outcomes,
    }))
}

fn validate_contract(contract: &MaximumHoldContract) -> Result<(), String> {
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.performance_gate
        || contract.balance_gate
    {
        return Err("maximum-hold contract grants forbidden authority or gating".into());
    }
    Ok(())
}

fn validate_summary(
    summary: &MaximumHoldSummary,
    providers: &BTreeMap<String, MaximumHoldProviderSummary>,
) -> Result<(), String> {
    if summary.extended + summary.exited != summary.observed
        || summary.provider_symbols != providers.len()
    {
        return Err("maximum-hold summary counts are inconsistent".into());
    }
    let totals = providers.values().fold([0_usize; 3], |mut total, value| {
        total[0] += value.observed;
        total[1] += value.extended;
        total[2] += value.exited;
        total
    });
    if totals != [summary.observed, summary.extended, summary.exited]
        || providers
            .values()
            .any(|value| value.extended + value.exited != value.observed)
    {
        return Err("maximum-hold provider counts are inconsistent".into());
    }
    Ok(())
}

fn validate_decisions(
    raw: Vec<MaximumHoldDecisionRaw>,
    observed: usize,
) -> Result<Vec<CohortMaximumHoldDecision>, String> {
    if raw.len() > observed || raw.len() > 50 {
        return Err("maximum-hold latest-decision window is inconsistent".into());
    }
    let mut identities = HashSet::new();
    raw.into_iter()
        .map(|decision| {
            if !identities.insert(decision.decision_id.clone()) {
                return Err("maximum-hold latest decisions contain a duplicate".into());
            }
            validate_decision(decision)
        })
        .collect()
}

fn validate_decision(value: MaximumHoldDecisionRaw) -> Result<CohortMaximumHoldDecision, String> {
    validate_identity(&value)?;
    validate_timing(&value)?;
    validate_outcome(&value)?;
    validate_scores(&value)?;
    validate_evaluations(&value)?;
    Ok(CohortMaximumHoldDecision {
        decision_id: value.decision_id,
        lifecycle_id: value.lifecycle_id,
        symbol: value.symbol,
        strategy_id: value.strategy_id,
        side: value.side,
        decision_time_ms: value.decision_time_ms,
        opened_at_ms: value.opened_at_ms,
        elapsed_ms: value.elapsed_ms,
        soft_deadline_timestamp_ms: value.soft_deadline_timestamp_ms,
        hard_deadline_timestamp_ms: value.hard_deadline_timestamp_ms,
        outcome: value.outcome,
        exit_reason: value.exit_reason,
        structure_alignment_score: value.structure_alignment_score,
        structure_alignment_threshold: value.structure_alignment_threshold,
    })
}

fn validate_identity(value: &MaximumHoldDecisionRaw) -> Result<(), String> {
    let expected = format!("{}:soft_maximum_hold", value.lifecycle_id);
    let lifecycle_prefix = format!("{}:", value.symbol);
    if value.decision_id != expected
        || !value.lifecycle_id.starts_with(&lifecycle_prefix)
        || value.strategy_id.trim().is_empty()
    {
        return Err("maximum-hold decision identity is inconsistent".into());
    }
    Ok(())
}

fn validate_timing(value: &MaximumHoldDecisionRaw) -> Result<(), String> {
    if value.decision_time_ms.checked_sub(value.opened_at_ms) != Some(value.elapsed_ms)
        || value.decision_time_ms < value.soft_deadline_timestamp_ms
        || value
            .hard_deadline_timestamp_ms
            .is_some_and(|hard| hard <= value.soft_deadline_timestamp_ms)
    {
        return Err("maximum-hold decision timing is inconsistent".into());
    }
    Ok(())
}

fn validate_outcome(value: &MaximumHoldDecisionRaw) -> Result<(), String> {
    let coherent = match value.outcome.as_str() {
        "extend" => value.exit_reason.is_none(),
        "exit" => value
            .exit_reason
            .as_ref()
            .is_some_and(|reason| !reason.trim().is_empty()),
        _ => false,
    };
    if !matches!(value.side.as_str(), "long" | "short") || !coherent {
        return Err("maximum-hold decision outcome is inconsistent".into());
    }
    Ok(())
}

fn validate_scores(value: &MaximumHoldDecisionRaw) -> Result<(), String> {
    let score_valid = value
        .structure_alignment_score
        .is_none_or(|score| score.is_finite() && (-1.0..=1.0).contains(&score));
    let threshold = value.structure_alignment_threshold;
    if !score_valid || !threshold.is_finite() || !(0.0..=1.0).contains(&threshold) {
        return Err("maximum-hold alignment evidence is invalid".into());
    }
    Ok(())
}

fn validate_evaluations(value: &MaximumHoldDecisionRaw) -> Result<(), String> {
    let invalid = [&value.provider_evaluation, &value.canonical_evaluation]
        .into_iter()
        .flatten()
        .any(|evaluation| !evaluation.is_object());
    if invalid {
        return Err("maximum-hold evaluation evidence must be an object".into());
    }
    Ok(())
}
