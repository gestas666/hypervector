//! Strict projection of the frozen prospective HIP-3 Swing/HA 60/30 observer.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort_profit_lock::{ContractRaw, PolicyRaw, report_only_contract};

const MODE: &str = "hip3_swing_60_30_prospective_observer_v1";
const SCOPE: &str = "hip3_swing_entries_at_or_after_predeclared_cutoff";
const ORIGIN: &str = "hip3_swing_profit_lock_hypothesis_20260809";
const HYPOTHESIS: &str = "hip3-swing-profit-lock";
const PREDECLARED_AT: &str = "2026-08-09T04:04:06Z";
const CUTOFF_MS: u64 = 1_786_248_246_000;
const POLICY_ID: &str = "a60_floor15_trail30";
const STRATEGY_SYMBOL_SCOPE: [&str; 5] = [
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SP500",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
];
const TOLERANCE: f64 = 0.000_001;

/// Frozen prospective observer state displayed by the research cockpit.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHip3ProfitLockProspectiveEvidence {
    pub entry_cutoff_timestamp_ms: u64,
    pub source_matching_lifecycles: usize,
    pub excluded_predeclaration_lifecycles: usize,
    pub prospective_lifecycles: usize,
    pub eligible_lifecycles: usize,
    pub triggered_lifecycles: usize,
    pub mean_delta_bps: Option<f64>,
    pub evidence_state: String,
}

#[derive(Debug, Deserialize)]
struct RawEvidence {
    schema_version: u64,
    mode: String,
    scope: String,
    policy_origin: String,
    hypothesis_id: String,
    predeclared_at_utc: String,
    entry_cutoff_timestamp_ms: u64,
    strategy_symbol_scope: Vec<String>,
    source_matching_lifecycles: usize,
    excluded_predeclaration_lifecycles: usize,
    prospective_lifecycles: usize,
    discovery_lifecycle_excluded: bool,
    evidence_state: String,
    contract: ContractRaw,
    policies: Vec<PolicyRaw>,
    profile_contracts_may_differ: bool,
    source_profile_count: usize,
    source_run_count: usize,
    summary_by_policy: BTreeMap<String, RawSummary>,
    by_provider_symbol: BTreeMap<String, RawPartition>,
}

#[derive(Debug, Deserialize)]
struct RawPartition {
    summary_by_policy: BTreeMap<String, RawSummary>,
}

#[derive(Debug, Deserialize)]
struct RawSummary {
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

#[derive(Debug)]
struct Summary {
    lifecycles: usize,
    eligible: usize,
    triggered: usize,
    mean_estimated_bps: Option<f64>,
    mean_actual_bps: Option<f64>,
    mean_delta_bps: Option<f64>,
}

pub(crate) fn parse(value: Value) -> Result<CohortHip3ProfitLockProspectiveEvidence, String> {
    let raw: RawEvidence = serde_json::from_value(value)
        .map_err(|error| format!("invalid HIP-3 prospective evidence: {error}"))?;
    validate_envelope(&raw)?;
    let total = project_policy_summary(&raw.summary_by_policy)?;
    validate_counts(&raw, &total)?;
    validate_provider_partitions(&raw.by_provider_symbol, &total)?;
    Ok(CohortHip3ProfitLockProspectiveEvidence {
        entry_cutoff_timestamp_ms: raw.entry_cutoff_timestamp_ms,
        source_matching_lifecycles: raw.source_matching_lifecycles,
        excluded_predeclaration_lifecycles: raw.excluded_predeclaration_lifecycles,
        prospective_lifecycles: raw.prospective_lifecycles,
        eligible_lifecycles: total.eligible,
        triggered_lifecycles: total.triggered,
        mean_delta_bps: total.mean_delta_bps,
        evidence_state: raw.evidence_state,
    })
}

fn validate_envelope(raw: &RawEvidence) -> Result<(), String> {
    let expected_scope = STRATEGY_SYMBOL_SCOPE.map(str::to_string);
    let policy = raw.policies.as_slice();
    let valid_policy = matches!(policy, [value]
        if value.policy_id == POLICY_ID
            && close(value.activation_bps, 60.0)
            && close(value.floor_bps, 15.0)
            && close(value.trailing_giveback_bps, 30.0));
    let valid = raw.schema_version == 1
        && raw.mode == MODE
        && raw.scope == SCOPE
        && raw.policy_origin == ORIGIN
        && raw.hypothesis_id == HYPOTHESIS
        && raw.predeclared_at_utc == PREDECLARED_AT
        && raw.entry_cutoff_timestamp_ms == CUTOFF_MS
        && raw.strategy_symbol_scope == expected_scope
        && raw.discovery_lifecycle_excluded
        && raw.profile_contracts_may_differ
        && report_only_contract(&raw.contract)
        && valid_policy;
    if !valid {
        return Err("HIP-3 prospective evidence changes the frozen contract".into());
    }
    Ok(())
}

fn validate_counts(raw: &RawEvidence, total: &Summary) -> Result<(), String> {
    let expected_state = if raw.prospective_lifecycles == 0 {
        "awaiting_post_cutoff_resolution"
    } else {
        "prospective_resolutions_observed"
    };
    let source_counts_valid = if raw.prospective_lifecycles == 0 {
        raw.source_profile_count == 0 && raw.source_run_count == 0
    } else {
        raw.source_profile_count > 0 && raw.source_run_count > 0
    };
    let valid = raw.source_matching_lifecycles
        == raw.excluded_predeclaration_lifecycles + raw.prospective_lifecycles
        && total.lifecycles == raw.prospective_lifecycles
        && raw.evidence_state == expected_state
        && source_counts_valid;
    if !valid {
        return Err("HIP-3 prospective lifecycle counts are inconsistent".into());
    }
    Ok(())
}

fn validate_provider_partitions(
    raw: &BTreeMap<String, RawPartition>,
    total: &Summary,
) -> Result<(), String> {
    let allowed = STRATEGY_SYMBOL_SCOPE.into_iter().collect::<BTreeSet<_>>();
    let mut partitions = Vec::with_capacity(raw.len());
    for (key, value) in raw {
        if !allowed.contains(key.as_str()) {
            return Err("HIP-3 prospective provider scope is invalid".into());
        }
        partitions.push(project_policy_summary(&value.summary_by_policy)?);
    }
    if partitions
        .iter()
        .map(|value| value.lifecycles)
        .sum::<usize>()
        != total.lifecycles
        || partitions.iter().map(|value| value.eligible).sum::<usize>() != total.eligible
        || partitions
            .iter()
            .map(|value| value.triggered)
            .sum::<usize>()
            != total.triggered
        || !weighted_means_match(&partitions, total)
    {
        return Err("HIP-3 prospective provider summaries do not reconcile".into());
    }
    Ok(())
}

fn project_policy_summary(raw: &BTreeMap<String, RawSummary>) -> Result<Summary, String> {
    if raw.len() != 1 || !raw.contains_key(POLICY_ID) {
        return Err("HIP-3 prospective policy summary is invalid".into());
    }
    project_summary(&raw[POLICY_ID])
}

fn project_summary(raw: &RawSummary) -> Result<Summary, String> {
    let means = [
        raw.mean_estimated_net_return_bps,
        raw.mean_actual_net_return_bps,
        raw.mean_delta_net_return_bps,
    ];
    let counts_valid = raw.eligible_lifecycles + raw.withheld_lifecycles == raw.lifecycles
        && raw.triggered <= raw.eligible_lifecycles
        && raw.wins + raw.losses <= raw.eligible_lifecycles;
    let means_valid = if raw.eligible_lifecycles == 0 {
        means.iter().all(Option::is_none)
    } else {
        means.iter().all(|value| value.is_some_and(f64::is_finite))
    };
    let delta_valid = match means {
        [Some(estimated), Some(actual), Some(delta)] => close(estimated - actual, delta),
        [None, None, None] => true,
        _ => false,
    };
    let profit_factor_valid = raw
        .normalized_profit_factor
        .is_none_or(|value| value.is_finite() && value >= 0.0);
    if !counts_valid || !means_valid || !delta_valid || !profit_factor_valid {
        return Err("HIP-3 prospective summary is inconsistent".into());
    }
    Ok(Summary {
        lifecycles: raw.lifecycles,
        eligible: raw.eligible_lifecycles,
        triggered: raw.triggered,
        mean_estimated_bps: means[0],
        mean_actual_bps: means[1],
        mean_delta_bps: means[2],
    })
}

fn weighted_means_match(partitions: &[Summary], total: &Summary) -> bool {
    close_option(
        weighted_mean(partitions, |value| value.mean_estimated_bps),
        total.mean_estimated_bps,
    ) && close_option(
        weighted_mean(partitions, |value| value.mean_actual_bps),
        total.mean_actual_bps,
    ) && close_option(
        weighted_mean(partitions, |value| value.mean_delta_bps),
        total.mean_delta_bps,
    )
}

fn weighted_mean(values: &[Summary], field: impl Fn(&Summary) -> Option<f64>) -> Option<f64> {
    let eligible = values.iter().map(|value| value.eligible).sum::<usize>();
    if eligible == 0 {
        return None;
    }
    Some(
        values
            .iter()
            .map(|value| field(value).unwrap_or(0.0) * value.eligible as f64)
            .sum::<f64>()
            / eligible as f64,
    )
}

fn close_option(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => close(left, right),
        (None, None) => true,
        _ => false,
    }
}

fn close(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= TOLERANCE
}
