//! Strict projection of causal report-only profit-lock challenger evidence.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;
use serde_json::Value;

const MODE: &str = "cohort_profit_lock_challenger_v1";
const SCOPE: &str = "compatible_profile_history";
pub(crate) const ORIGIN: &str = "existing_predeclared_hype_profit_research_v1";
const MONEY_TOLERANCE: f64 = 0.000_001;
const POLICIES: [(&str, f64, f64, f64); 3] = [
    ("a25_floor15_trail10", 25.0, 15.0, 10.0),
    ("a40_floor15_trail20", 40.0, 15.0, 20.0),
    ("a60_floor15_trail30", 60.0, 15.0, 30.0),
];

/// Aggregate economics for one frozen profit-lock policy.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockSummary {
    pub eligible: usize,
    pub triggered: usize,
    pub estimated_net_usd: f64,
    pub actual_net_usd: f64,
    pub delta_net_usd: f64,
    pub profit_factor: Option<f64>,
}

/// One validated lifecycle partition of frozen policy results.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockPartition {
    pub closed_lifecycles: usize,
    pub summary_by_policy: BTreeMap<String, CohortProfitLockSummary>,
}

/// Execution-incapable profit-lock evidence exposed to the TUI.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockEvidence {
    pub summary_by_policy: BTreeMap<String, CohortProfitLockSummary>,
    pub by_provider_symbol: BTreeMap<String, CohortProfitLockPartition>,
    pub current_run: CohortProfitLockPartition,
    pub all_time_live_mechanism: Option<CohortProfitLockNormalizedEvidence>,
    pub support_decay_all_time_live_mechanism: Option<CohortSupportDecayProfitLockEvidence>,
    pub hip3_swing_60_30_prospective_mechanism: Option<CohortHip3ProfitLockProspectiveEvidence>,
}

pub use crate::backend_cohort_hip3_profit_lock::CohortHip3ProfitLockProspectiveEvidence;

pub use crate::backend_cohort_profit_lock_normalized::{
    CohortProfitLockNormalizedEvidence, CohortProfitLockNormalizedPartition,
    CohortProfitLockNormalizedSummary, CohortSupportDecayProfitLockEvidence,
};
use crate::backend_cohort_profit_lock_normalized::{
    parse_normalized_profit_lock_evidence, parse_support_decay_profit_lock_evidence,
};

#[derive(Debug, Deserialize)]
struct EvidenceRaw {
    schema_version: u64,
    mode: String,
    scope: String,
    policy_origin: String,
    contract: ContractRaw,
    policies: Vec<PolicyRaw>,
    summary_by_policy: BTreeMap<String, SummaryRaw>,
    by_provider_symbol: BTreeMap<String, PartitionRaw>,
    current_run: CurrentRunRaw,
    #[serde(default)]
    all_time_live_mechanism: Option<Value>,
    #[serde(default)]
    support_decay_all_time_live_mechanism: Option<Value>,
    #[serde(default)]
    hip3_swing_60_30_prospective_mechanism: Option<Value>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ContractRaw {
    pub(crate) report_only: bool,
    pub(crate) execution_authority: String,
    pub(crate) runtime_strategy_changed: bool,
    pub(crate) automatic_strategy_changes: bool,
    pub(crate) automatic_promotion: bool,
    pub(crate) performance_gate: bool,
    pub(crate) balance_gate: bool,
    pub(crate) portfolio_pnl_claimed: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct PolicyRaw {
    pub(crate) policy_id: String,
    pub(crate) activation_bps: f64,
    pub(crate) floor_bps: f64,
    pub(crate) trailing_giveback_bps: f64,
}

#[derive(Debug, Deserialize)]
struct SummaryRaw {
    lifecycles: usize,
    eligible_lifecycles: usize,
    withheld_lifecycles: usize,
    triggered: usize,
    wins: usize,
    losses: usize,
    estimated_net_pnl_usd: f64,
    actual_net_pnl_usd: f64,
    estimated_minus_actual_net_usd: f64,
    profit_factor: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct PartitionRaw {
    summary_by_policy: BTreeMap<String, SummaryRaw>,
}

#[derive(Debug, Deserialize)]
struct CurrentRunRaw {
    run_id: String,
    summary_by_policy: BTreeMap<String, SummaryRaw>,
}

/// Parse and validate report-only profit-lock evidence from a live checkpoint.
pub fn parse_profit_lock_evidence(
    value: Option<Value>,
) -> Result<Option<CohortProfitLockEvidence>, String> {
    let Some(value) = value else {
        return Ok(None);
    };
    let raw: EvidenceRaw = serde_json::from_value(value)
        .map_err(|error| format!("invalid profit-lock evidence: {error}"))?;
    validate_envelope(&raw)?;
    let total = project_partition(raw.summary_by_policy)?;
    let grouped = project_grouped(raw.by_provider_symbol)?;
    validate_grouped(&total, &grouped)?;
    if raw.current_run.run_id.trim().is_empty() {
        return Err("profit-lock current-run identity is invalid".into());
    }
    let current_run = project_partition(raw.current_run.summary_by_policy)?;
    if current_run.closed_lifecycles > total.closed_lifecycles {
        return Err("profit-lock current-run count exceeds archive".into());
    }
    let all_time_live_mechanism = raw
        .all_time_live_mechanism
        .map(parse_normalized_profit_lock_evidence)
        .transpose()?;
    let support_decay_all_time_live_mechanism = raw
        .support_decay_all_time_live_mechanism
        .map(parse_support_decay_profit_lock_evidence)
        .transpose()?;
    let hip3_swing_60_30_prospective_mechanism = raw
        .hip3_swing_60_30_prospective_mechanism
        .map(crate::backend_cohort_hip3_profit_lock::parse)
        .transpose()?;
    Ok(Some(CohortProfitLockEvidence {
        summary_by_policy: total.summary_by_policy,
        by_provider_symbol: grouped,
        current_run,
        all_time_live_mechanism,
        support_decay_all_time_live_mechanism,
        hip3_swing_60_30_prospective_mechanism,
    }))
}

fn validate_envelope(raw: &EvidenceRaw) -> Result<(), String> {
    if raw.schema_version != 1
        || raw.mode != MODE
        || raw.scope != SCOPE
        || raw.policy_origin != ORIGIN
        || !report_only_contract(&raw.contract)
    {
        return Err("profit-lock contract grants authority or changes frozen scope".into());
    }
    validate_policies(&raw.policies)
}

pub(crate) fn report_only_contract(contract: &ContractRaw) -> bool {
    contract.report_only
        && contract.execution_authority == "none"
        && !contract.runtime_strategy_changed
        && !contract.automatic_strategy_changes
        && !contract.automatic_promotion
        && !contract.performance_gate
        && !contract.balance_gate
        && !contract.portfolio_pnl_claimed
}

pub(crate) fn validate_policies(raw: &[PolicyRaw]) -> Result<(), String> {
    if raw.len() != POLICIES.len() {
        return Err("profit-lock frozen policies are incomplete".into());
    }
    for (policy, expected) in raw.iter().zip(POLICIES) {
        let observed = (
            policy.policy_id.as_str(),
            policy.activation_bps,
            policy.floor_bps,
            policy.trailing_giveback_bps,
        );
        if observed != expected {
            return Err("profit-lock frozen policy definition changed".into());
        }
    }
    Ok(())
}

fn project_partition(
    raw: BTreeMap<String, SummaryRaw>,
) -> Result<CohortProfitLockPartition, String> {
    validate_policy_keys(&raw)?;
    let counts = raw
        .values()
        .map(|value| value.lifecycles)
        .collect::<BTreeSet<_>>();
    if counts.len() != 1 {
        return Err("profit-lock lifecycle counts disagree across policies".into());
    }
    let closed_lifecycles = counts.first().copied().unwrap_or(0);
    let summary_by_policy = raw
        .into_iter()
        .map(|(key, value)| Ok((key, project_summary(value)?)))
        .collect::<Result<_, String>>()?;
    Ok(CohortProfitLockPartition {
        closed_lifecycles,
        summary_by_policy,
    })
}

fn validate_policy_keys<T>(raw: &BTreeMap<String, T>) -> Result<(), String> {
    let observed = raw.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = POLICIES.map(|value| value.0).into_iter().collect();
    if observed != expected {
        return Err("profit-lock summary policies are inconsistent".into());
    }
    Ok(())
}

fn project_summary(raw: SummaryRaw) -> Result<CohortProfitLockSummary, String> {
    let counts_valid = raw.eligible_lifecycles + raw.withheld_lifecycles == raw.lifecycles
        && raw.triggered <= raw.eligible_lifecycles
        && raw.wins + raw.losses <= raw.eligible_lifecycles;
    let economics = [
        raw.estimated_net_pnl_usd,
        raw.actual_net_pnl_usd,
        raw.estimated_minus_actual_net_usd,
    ];
    let profit_factor_valid = raw
        .profit_factor
        .is_none_or(|value| value.is_finite() && value >= 0.0);
    if !counts_valid
        || economics.into_iter().any(|value| !value.is_finite())
        || !profit_factor_valid
        || !close(
            raw.estimated_net_pnl_usd - raw.actual_net_pnl_usd,
            raw.estimated_minus_actual_net_usd,
        )
    {
        return Err("profit-lock summary economics are inconsistent".into());
    }
    Ok(CohortProfitLockSummary {
        eligible: raw.eligible_lifecycles,
        triggered: raw.triggered,
        estimated_net_usd: raw.estimated_net_pnl_usd,
        actual_net_usd: raw.actual_net_pnl_usd,
        delta_net_usd: raw.estimated_minus_actual_net_usd,
        profit_factor: raw.profit_factor,
    })
}

fn project_grouped(
    raw: BTreeMap<String, PartitionRaw>,
) -> Result<BTreeMap<String, CohortProfitLockPartition>, String> {
    raw.into_iter()
        .map(|(key, value)| {
            if !key.contains('|') || key.starts_with('|') || key.ends_with('|') {
                return Err("profit-lock provider identity is invalid".into());
            }
            Ok((key, project_partition(value.summary_by_policy)?))
        })
        .collect()
}

fn validate_grouped(
    total: &CohortProfitLockPartition,
    grouped: &BTreeMap<String, CohortProfitLockPartition>,
) -> Result<(), String> {
    let grouped_count: usize = grouped.values().map(|value| value.closed_lifecycles).sum();
    if grouped_count != total.closed_lifecycles {
        return Err("profit-lock provider lifecycle totals disagree".into());
    }
    for policy_id in POLICIES.map(|value| value.0) {
        let expected = &total.summary_by_policy[policy_id];
        let eligible: usize = grouped
            .values()
            .map(|value| value.summary_by_policy[policy_id].eligible)
            .sum();
        let estimated: f64 = grouped
            .values()
            .map(|value| value.summary_by_policy[policy_id].estimated_net_usd)
            .sum();
        let actual: f64 = grouped
            .values()
            .map(|value| value.summary_by_policy[policy_id].actual_net_usd)
            .sum();
        if eligible != expected.eligible
            || !close(estimated, expected.estimated_net_usd)
            || !close(actual, expected.actual_net_usd)
        {
            return Err("profit-lock provider economics disagree with archive".into());
        }
    }
    Ok(())
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= MONEY_TOLERANCE
}
