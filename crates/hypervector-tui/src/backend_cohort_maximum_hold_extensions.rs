//! Strict projection of report-only post-soft-deadline outcome evidence.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort_post_soft_trail::{
    CohortPostSoftTrailEvidence, PostSoftTrailEvidenceRaw, project_post_soft_trail,
};

const MODE: &str = "cohort_maximum_hold_extension_outcomes";
const LATEST_LIMIT: usize = 50;
const MONEY_TOLERANCE: f64 = 0.000_001;

#[derive(Debug, Clone, PartialEq)]
pub struct CohortMaximumHoldExtensionEvidence {
    pub resolved: usize,
    pub inferred_without_decision_event: usize,
    pub better_than_soft_reference: usize,
    pub worse_than_soft_reference: usize,
    pub unchanged_from_soft_reference: usize,
    pub actual_net_pnl_usd: f64,
    pub estimated_soft_net_pnl_usd: f64,
    pub actual_minus_soft_net_usd: f64,
    pub latest_outcomes: Vec<CohortMaximumHoldExtensionOutcome>,
    pub post_soft_trail_challenger: Option<CohortPostSoftTrailEvidence>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortMaximumHoldExtensionOutcome {
    pub lifecycle_id: String,
    pub symbol: String,
    pub strategy_id: String,
    pub side: String,
    pub extension_duration_ms: u64,
    pub causal_decision_recorded: bool,
    pub actual_net_pnl_usd: f64,
    pub estimated_soft_net_pnl_usd: f64,
    pub actual_minus_soft_net_usd: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct MaximumHoldExtensionEvidenceRaw {
    schema_version: u64,
    mode: String,
    contract: ExtensionContractRaw,
    summary: ExtensionSummaryRaw,
    by_provider_symbol: BTreeMap<String, ExtensionSummaryRaw>,
    latest_outcomes: Vec<ExtensionOutcomeRaw>,
    #[serde(default)]
    post_soft_trail_challenger: Option<PostSoftTrailEvidenceRaw>,
}

#[derive(Debug, Deserialize)]
struct ExtensionContractRaw {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct ExtensionSummaryRaw {
    bound_extension_lifecycles: usize,
    resolved: usize,
    inferred_without_decision_event: usize,
    better_than_soft_reference: usize,
    worse_than_soft_reference: usize,
    unchanged_from_soft_reference: usize,
    actual_net_pnl_usd: f64,
    estimated_soft_net_pnl_usd: f64,
    actual_minus_soft_net_usd: f64,
}

#[derive(Debug, Deserialize)]
struct ExtensionOutcomeRaw {
    status: String,
    lifecycle_id: String,
    symbol: String,
    strategy_id: String,
    side: String,
    opened_at_ms: u64,
    soft_deadline_timestamp_ms: u64,
    hard_deadline_timestamp_ms: u64,
    actual_exit_timestamp_ms: u64,
    extension_duration_ms: u64,
    causal_decision_recorded: bool,
    decision_outcome: Option<String>,
    evidence_basis: String,
    actual_net_pnl_usd: f64,
    estimated_soft_net_pnl_usd: f64,
    actual_minus_soft_net_usd: f64,
}

pub(crate) fn project_maximum_hold_extension_outcomes(
    raw: Option<MaximumHoldExtensionEvidenceRaw>,
) -> Result<Option<CohortMaximumHoldExtensionEvidence>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_envelope(&raw)?;
    validate_summary(&raw.summary)?;
    validate_grouped(&raw.summary, &raw.by_provider_symbol)?;
    let latest_outcomes = validate_outcomes(raw.latest_outcomes, raw.summary.resolved)?;
    let post_soft_trail_challenger = project_post_soft_trail(raw.post_soft_trail_challenger)?;
    Ok(Some(CohortMaximumHoldExtensionEvidence {
        resolved: raw.summary.resolved,
        inferred_without_decision_event: raw.summary.inferred_without_decision_event,
        better_than_soft_reference: raw.summary.better_than_soft_reference,
        worse_than_soft_reference: raw.summary.worse_than_soft_reference,
        unchanged_from_soft_reference: raw.summary.unchanged_from_soft_reference,
        actual_net_pnl_usd: raw.summary.actual_net_pnl_usd,
        estimated_soft_net_pnl_usd: raw.summary.estimated_soft_net_pnl_usd,
        actual_minus_soft_net_usd: raw.summary.actual_minus_soft_net_usd,
        latest_outcomes,
        post_soft_trail_challenger,
    }))
}

fn validate_envelope(raw: &MaximumHoldExtensionEvidenceRaw) -> Result<(), String> {
    let contract = &raw.contract;
    if raw.schema_version != 1
        || raw.mode != MODE
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
        || contract.performance_gate
        || contract.balance_gate
    {
        return Err("maximum-hold extension contract grants authority or gating".into());
    }
    Ok(())
}

fn validate_summary(value: &ExtensionSummaryRaw) -> Result<(), String> {
    let classified = value
        .better_than_soft_reference
        .checked_add(value.worse_than_soft_reference)
        .and_then(|count| count.checked_add(value.unchanged_from_soft_reference));
    if value.bound_extension_lifecycles != value.resolved
        || classified != Some(value.resolved)
        || value.inferred_without_decision_event > value.resolved
        || !economics_valid(value)
    {
        return Err("maximum-hold extension summary is inconsistent".into());
    }
    Ok(())
}

fn validate_grouped(
    total: &ExtensionSummaryRaw,
    grouped: &BTreeMap<String, ExtensionSummaryRaw>,
) -> Result<(), String> {
    for (key, value) in grouped {
        if key.trim().is_empty() || !key.contains('|') {
            return Err("maximum-hold extension provider identity is invalid".into());
        }
        validate_summary(value)?;
    }
    let counts = grouped.values().fold([0_usize; 5], |mut sums, value| {
        sums[0] += value.resolved;
        sums[1] += value.inferred_without_decision_event;
        sums[2] += value.better_than_soft_reference;
        sums[3] += value.worse_than_soft_reference;
        sums[4] += value.unchanged_from_soft_reference;
        sums
    });
    let expected = [
        total.resolved,
        total.inferred_without_decision_event,
        total.better_than_soft_reference,
        total.worse_than_soft_reference,
        total.unchanged_from_soft_reference,
    ];
    if counts != expected || !grouped_economics_match(total, grouped) {
        return Err("maximum-hold extension provider totals are inconsistent".into());
    }
    Ok(())
}

fn grouped_economics_match(
    total: &ExtensionSummaryRaw,
    grouped: &BTreeMap<String, ExtensionSummaryRaw>,
) -> bool {
    let actual = grouped.values().map(|value| value.actual_net_pnl_usd).sum();
    let soft = grouped
        .values()
        .map(|value| value.estimated_soft_net_pnl_usd)
        .sum();
    let delta = grouped
        .values()
        .map(|value| value.actual_minus_soft_net_usd)
        .sum();
    close(actual, total.actual_net_pnl_usd)
        && close(soft, total.estimated_soft_net_pnl_usd)
        && close(delta, total.actual_minus_soft_net_usd)
}

fn economics_valid(value: &ExtensionSummaryRaw) -> bool {
    let values = [
        value.actual_net_pnl_usd,
        value.estimated_soft_net_pnl_usd,
        value.actual_minus_soft_net_usd,
    ];
    values.into_iter().all(f64::is_finite)
        && close(
            value.actual_net_pnl_usd - value.estimated_soft_net_pnl_usd,
            value.actual_minus_soft_net_usd,
        )
}

fn validate_outcomes(
    raw: Vec<ExtensionOutcomeRaw>,
    resolved: usize,
) -> Result<Vec<CohortMaximumHoldExtensionOutcome>, String> {
    if raw.len() > resolved || raw.len() > LATEST_LIMIT {
        return Err("maximum-hold extension outcome window is inconsistent".into());
    }
    raw.into_iter().map(validate_outcome).collect()
}

fn validate_outcome(
    value: ExtensionOutcomeRaw,
) -> Result<CohortMaximumHoldExtensionOutcome, String> {
    let identity = value.lifecycle_id == format!("{}:{}", value.symbol, oid(&value)?)
        && !value.strategy_id.trim().is_empty();
    let timing = value.opened_at_ms < value.soft_deadline_timestamp_ms
        && value.soft_deadline_timestamp_ms < value.hard_deadline_timestamp_ms
        && value.actual_exit_timestamp_ms > value.soft_deadline_timestamp_ms
        && value.actual_exit_timestamp_ms - value.soft_deadline_timestamp_ms
            == value.extension_duration_ms;
    let decision = match value.causal_decision_recorded {
        true => value.decision_outcome.as_deref() == Some("extend"),
        false => value.decision_outcome.is_none(),
    };
    if value.status != "resolved"
        || !identity
        || !timing
        || !decision
        || !matches!(value.side.as_str(), "long" | "short")
        || value.evidence_basis != "persisted_runtime_plan_plus_resolved_execution"
        || !outcome_economics_valid(&value)
    {
        return Err("maximum-hold extension outcome is inconsistent".into());
    }
    Ok(CohortMaximumHoldExtensionOutcome {
        lifecycle_id: value.lifecycle_id,
        symbol: value.symbol,
        strategy_id: value.strategy_id,
        side: value.side,
        extension_duration_ms: value.extension_duration_ms,
        causal_decision_recorded: value.causal_decision_recorded,
        actual_net_pnl_usd: value.actual_net_pnl_usd,
        estimated_soft_net_pnl_usd: value.estimated_soft_net_pnl_usd,
        actual_minus_soft_net_usd: value.actual_minus_soft_net_usd,
    })
}

fn oid(value: &ExtensionOutcomeRaw) -> Result<u64, String> {
    value
        .lifecycle_id
        .split_once(':')
        .and_then(|(_, raw)| raw.parse().ok())
        .filter(|oid| *oid > 0)
        .ok_or_else(|| "maximum-hold extension lifecycle oid is invalid".into())
}

fn outcome_economics_valid(value: &ExtensionOutcomeRaw) -> bool {
    [
        value.actual_net_pnl_usd,
        value.estimated_soft_net_pnl_usd,
        value.actual_minus_soft_net_usd,
    ]
    .into_iter()
    .all(f64::is_finite)
        && close(
            value.actual_net_pnl_usd - value.estimated_soft_net_pnl_usd,
            value.actual_minus_soft_net_usd,
        )
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= MONEY_TOLERANCE
}
