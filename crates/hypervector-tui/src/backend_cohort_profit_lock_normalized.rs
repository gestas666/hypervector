//! Strict normalized projections for report-only profit-lock mechanisms.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort_profit_lock::{
    ContractRaw, ORIGIN, PolicyRaw, report_only_contract, validate_policies,
};

const NORMALIZED_MODE: &str = "cohort_profit_lock_normalized_mechanism_v1";
const NORMALIZED_SCOPE: &str = "all_live_history_normalized_mechanism";
const SUPPORT_DECAY_MODE: &str = "cohort_support_decay_profit_lock_mechanism_v1";
const SUPPORT_DECAY_ORIGIN: &str = "post_hoc_open_sol_profit_giveback_hypothesis_20260807";
const SUPPORT_DECAY_SOURCE: &str = "causal_regime_support_decay_persistence_v1";
const SUPPORT_DECAY_THRESHOLD: f64 = 0.25;
const SUPPORT_DECAY_PERSISTENCE: usize = 5;
const SUPPORT_DECAY_INTERVAL_MS: u64 = 60_000;
const SOL_PROVIDER: &str = "hype_breakout_onset_bidirectional_v1|SOL";
const A40: &str = "a40_floor15_trail20";
const POLICY_IDS: [&str; 3] = [
    "a25_floor15_trail10",
    "a40_floor15_trail20",
    "a60_floor15_trail30",
];
const VALUE_TOLERANCE: f64 = 0.000_001;

/// Price-relative summary for one frozen policy across unlike live contracts.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockNormalizedSummary {
    pub eligible: usize,
    pub triggered: usize,
    pub mean_estimated_bps: Option<f64>,
    pub mean_actual_bps: Option<f64>,
    pub mean_delta_bps: Option<f64>,
    pub profit_factor: Option<f64>,
}

/// One provider partition of normalized all-live exit evidence.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockNormalizedPartition {
    pub closed_lifecycles: usize,
    pub summary_by_policy: BTreeMap<String, CohortProfitLockNormalizedSummary>,
}

/// Strictly validated all-live mechanism evidence without portfolio claims.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProfitLockNormalizedEvidence {
    pub source_profile_count: usize,
    pub source_run_count: usize,
    pub summary_by_policy: BTreeMap<String, CohortProfitLockNormalizedSummary>,
    pub by_provider_symbol: BTreeMap<String, CohortProfitLockNormalizedPartition>,
}

/// Post-hoc support-decay observer evidence with no execution authority.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortSupportDecayProfitLockEvidence {
    pub support_decay_threshold: f64,
    pub persistence_decisions: usize,
    pub decision_interval_ms: u64,
    pub same_bar_activation_and_trigger_allowed: bool,
    pub mechanism: CohortProfitLockNormalizedEvidence,
}

#[derive(Debug, Deserialize)]
struct NormalizedEnvelopeRaw {
    schema_version: u64,
    mode: String,
    scope: String,
    policy_origin: String,
    contract: ContractRaw,
    policies: Vec<PolicyRaw>,
    profile_contracts_may_differ: bool,
    source_profile_count: usize,
    source_run_count: usize,
    summary_by_policy: BTreeMap<String, NormalizedSummaryRaw>,
    by_provider_symbol: BTreeMap<String, NormalizedPartitionRaw>,
    #[serde(default)]
    activation_contract: Option<SupportDecayActivationRaw>,
}

#[derive(Debug, Deserialize)]
struct SupportDecayActivationRaw {
    source: String,
    persistence_decisions: usize,
    decision_interval_ms: u64,
    support_decay_threshold: f64,
    pre_gate_favorable_excursion_retained: bool,
    same_bar_activation_and_trigger_allowed: bool,
}

#[derive(Debug, Deserialize)]
struct NormalizedPartitionRaw {
    summary_by_policy: BTreeMap<String, NormalizedSummaryRaw>,
}

#[derive(Debug, Deserialize)]
struct NormalizedSummaryRaw {
    lifecycles: usize,
    eligible_lifecycles: usize,
    withheld_lifecycles: usize,
    triggered: usize,
    wins: usize,
    losses: usize,
    mean_estimated_net_return_bps: Option<f64>,
    mean_actual_net_return_bps: Option<f64>,
    mean_delta_net_return_bps: Option<f64>,
    normalized_profit_factor: Option<f64>,
}

pub(crate) fn parse_normalized_profit_lock_evidence(
    value: Value,
) -> Result<CohortProfitLockNormalizedEvidence, String> {
    let raw = parse_envelope(value, "normalized profit-lock")?;
    validate_envelope(&raw, NORMALIZED_MODE, ORIGIN, "normalized profit-lock")?;
    if raw.activation_contract.is_some() {
        return Err("normalized profit-lock activation contract is unexpected".into());
    }
    project_mechanism(raw).map_err(|error| format!("normalized profit-lock {error}"))
}

pub(crate) fn parse_support_decay_profit_lock_evidence(
    value: Value,
) -> Result<CohortSupportDecayProfitLockEvidence, String> {
    let raw = parse_envelope(value, "support-decay profit-lock")?;
    validate_envelope(
        &raw,
        SUPPORT_DECAY_MODE,
        SUPPORT_DECAY_ORIGIN,
        "support-decay profit-lock",
    )?;
    let activation = raw
        .activation_contract
        .as_ref()
        .ok_or_else(|| "support-decay activation contract is missing".to_string())?;
    validate_support_decay_activation(activation)?;
    let activation_values = (
        activation.support_decay_threshold,
        activation.persistence_decisions,
        activation.decision_interval_ms,
        activation.same_bar_activation_and_trigger_allowed,
    );
    let mechanism =
        project_mechanism(raw).map_err(|error| format!("support-decay profit-lock {error}"))?;
    validate_sol_observation(&mechanism)?;
    let result = CohortSupportDecayProfitLockEvidence {
        support_decay_threshold: activation_values.0,
        persistence_decisions: activation_values.1,
        decision_interval_ms: activation_values.2,
        same_bar_activation_and_trigger_allowed: activation_values.3,
        mechanism,
    };
    Ok(result)
}

fn validate_sol_observation(mechanism: &CohortProfitLockNormalizedEvidence) -> Result<(), String> {
    let sol = mechanism
        .by_provider_symbol
        .get(SOL_PROVIDER)
        .ok_or_else(|| "support-decay SOL provider observation is missing".to_string())?;
    let a40 = sol
        .summary_by_policy
        .get(A40)
        .ok_or_else(|| "support-decay SOL A40 observation is missing".to_string())?;
    if sol.closed_lifecycles == 0 || a40.eligible == 0 {
        return Err("support-decay SOL A40 observation is empty".into());
    }
    Ok(())
}

fn parse_envelope(value: Value, label: &str) -> Result<NormalizedEnvelopeRaw, String> {
    serde_json::from_value(value).map_err(|error| format!("invalid {label} evidence: {error}"))
}

fn validate_envelope(
    raw: &NormalizedEnvelopeRaw,
    expected_mode: &str,
    expected_origin: &str,
    label: &str,
) -> Result<(), String> {
    if raw.schema_version != 1
        || raw.mode != expected_mode
        || raw.scope != NORMALIZED_SCOPE
        || raw.policy_origin != expected_origin
        || !raw.profile_contracts_may_differ
        || !report_only_contract(&raw.contract)
    {
        return Err(format!("{label} evidence changes frozen report-only scope"));
    }
    validate_policies(&raw.policies).map_err(|error| format!("{label} {error}"))
}

fn validate_support_decay_activation(raw: &SupportDecayActivationRaw) -> Result<(), String> {
    let valid = raw.source == SUPPORT_DECAY_SOURCE
        && raw.persistence_decisions == SUPPORT_DECAY_PERSISTENCE
        && raw.decision_interval_ms == SUPPORT_DECAY_INTERVAL_MS
        && close(raw.support_decay_threshold, SUPPORT_DECAY_THRESHOLD)
        && raw.pre_gate_favorable_excursion_retained
        && !raw.same_bar_activation_and_trigger_allowed;
    if !valid {
        return Err("support-decay activation contract changed".into());
    }
    Ok(())
}

fn project_mechanism(
    raw: NormalizedEnvelopeRaw,
) -> Result<CohortProfitLockNormalizedEvidence, String> {
    let total = project_partition(raw.summary_by_policy)?;
    let grouped = project_grouped(raw.by_provider_symbol)?;
    validate_grouped(&total, &grouped)?;
    validate_source_counts(
        total.closed_lifecycles,
        raw.source_profile_count,
        raw.source_run_count,
    )?;
    Ok(CohortProfitLockNormalizedEvidence {
        source_profile_count: raw.source_profile_count,
        source_run_count: raw.source_run_count,
        summary_by_policy: total.summary_by_policy,
        by_provider_symbol: grouped,
    })
}

fn validate_source_counts(
    lifecycles: usize,
    source_profiles: usize,
    source_runs: usize,
) -> Result<(), String> {
    let empty_consistent = lifecycles > 0 || (source_profiles == 0 && source_runs == 0);
    let populated_consistent = lifecycles == 0 || (source_profiles > 0 && source_runs > 0);
    if !empty_consistent || !populated_consistent {
        return Err("source counts are inconsistent".into());
    }
    Ok(())
}

fn project_partition(
    raw: BTreeMap<String, NormalizedSummaryRaw>,
) -> Result<CohortProfitLockNormalizedPartition, String> {
    validate_policy_keys(&raw)?;
    let counts = raw
        .values()
        .map(|value| value.lifecycles)
        .collect::<BTreeSet<_>>();
    if counts.len() != 1 {
        return Err("lifecycle counts disagree".into());
    }
    let closed_lifecycles = counts.first().copied().unwrap_or(0);
    let summary_by_policy = raw
        .into_iter()
        .map(|(key, value)| Ok((key, project_summary(value)?)))
        .collect::<Result<_, String>>()?;
    Ok(CohortProfitLockNormalizedPartition {
        closed_lifecycles,
        summary_by_policy,
    })
}

fn validate_policy_keys<T>(raw: &BTreeMap<String, T>) -> Result<(), String> {
    let observed = raw.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = POLICY_IDS.into_iter().collect();
    if observed != expected {
        return Err("summary policies are inconsistent".into());
    }
    Ok(())
}

fn project_summary(raw: NormalizedSummaryRaw) -> Result<CohortProfitLockNormalizedSummary, String> {
    let counts_valid = raw.eligible_lifecycles + raw.withheld_lifecycles == raw.lifecycles
        && raw.triggered <= raw.eligible_lifecycles
        && raw.wins + raw.losses <= raw.eligible_lifecycles;
    let means = [
        raw.mean_estimated_net_return_bps,
        raw.mean_actual_net_return_bps,
        raw.mean_delta_net_return_bps,
    ];
    let means_valid = if raw.eligible_lifecycles == 0 {
        means.iter().all(Option::is_none)
    } else {
        means.iter().all(|value| value.is_some_and(f64::is_finite))
    };
    let profit_factor_valid = raw
        .normalized_profit_factor
        .is_none_or(|value| value.is_finite() && value >= 0.0);
    if !counts_valid || !means_valid || !delta_is_valid(&means) || !profit_factor_valid {
        return Err("summary is inconsistent".into());
    }
    Ok(CohortProfitLockNormalizedSummary {
        eligible: raw.eligible_lifecycles,
        triggered: raw.triggered,
        mean_estimated_bps: means[0],
        mean_actual_bps: means[1],
        mean_delta_bps: means[2],
        profit_factor: raw.normalized_profit_factor,
    })
}

fn delta_is_valid(means: &[Option<f64>; 3]) -> bool {
    match (means[0], means[1], means[2]) {
        (Some(estimated), Some(actual), Some(delta)) => close(estimated - actual, delta),
        (None, None, None) => true,
        _ => false,
    }
}

fn project_grouped(
    raw: BTreeMap<String, NormalizedPartitionRaw>,
) -> Result<BTreeMap<String, CohortProfitLockNormalizedPartition>, String> {
    raw.into_iter()
        .map(|(key, value)| {
            if !key.contains('|') || key.starts_with('|') || key.ends_with('|') {
                return Err("provider identity is invalid".into());
            }
            Ok((key, project_partition(value.summary_by_policy)?))
        })
        .collect()
}

fn validate_grouped(
    total: &CohortProfitLockNormalizedPartition,
    grouped: &BTreeMap<String, CohortProfitLockNormalizedPartition>,
) -> Result<(), String> {
    let grouped_count: usize = grouped.values().map(|value| value.closed_lifecycles).sum();
    if grouped_count != total.closed_lifecycles {
        return Err("provider counts disagree".into());
    }
    for policy_id in POLICY_IDS {
        validate_policy(total, grouped, policy_id)?;
    }
    Ok(())
}

fn validate_policy(
    total: &CohortProfitLockNormalizedPartition,
    grouped: &BTreeMap<String, CohortProfitLockNormalizedPartition>,
    policy_id: &str,
) -> Result<(), String> {
    let expected = &total.summary_by_policy[policy_id];
    let eligible: usize = grouped
        .values()
        .map(|value| value.summary_by_policy[policy_id].eligible)
        .sum();
    let fields: [fn(&CohortProfitLockNormalizedSummary) -> Option<f64>; 3] = [
        |value| value.mean_estimated_bps,
        |value| value.mean_actual_bps,
        |value| value.mean_delta_bps,
    ];
    let targets = [
        expected.mean_estimated_bps,
        expected.mean_actual_bps,
        expected.mean_delta_bps,
    ];
    let means_match = fields
        .into_iter()
        .zip(targets)
        .all(|(field, target)| optional_close(weighted_mean(grouped, policy_id, field), target));
    if eligible != expected.eligible || !means_match {
        return Err("provider economics disagree".into());
    }
    Ok(())
}

fn weighted_mean(
    grouped: &BTreeMap<String, CohortProfitLockNormalizedPartition>,
    policy_id: &str,
    field: fn(&CohortProfitLockNormalizedSummary) -> Option<f64>,
) -> Option<f64> {
    let mut weighted = 0.0;
    let mut count = 0;
    for partition in grouped.values() {
        let summary = &partition.summary_by_policy[policy_id];
        if let Some(value) = field(summary) {
            weighted += value * summary.eligible as f64;
            count += summary.eligible;
        }
    }
    (count > 0).then_some(weighted / count as f64)
}

fn optional_close(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => close(left, right),
        (None, None) => true,
        _ => false,
    }
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= VALUE_TOLERANCE
}
