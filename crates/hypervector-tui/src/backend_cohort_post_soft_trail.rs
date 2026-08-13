//! Strict projection of report-only post-soft protective-trail evidence.

use std::collections::{BTreeMap, BTreeSet, HashSet};

use serde::Deserialize;

const MODE: &str = "cohort_post_soft_trail_challenger_v1";
const POLICIES: [u16; 3] = [20, 30, 40];
const LATEST_LIMIT: usize = 50;
const MONEY_TOLERANCE: f64 = 0.000_001;

/// Aggregate counterfactual economics for one frozen giveback policy.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortPostSoftTrailSummary {
    pub eligible: usize,
    pub triggered: usize,
    pub not_triggered: usize,
    pub estimated_net_pnl_usd: f64,
    pub actual_net_pnl_usd: f64,
    pub estimated_soft_net_pnl_usd: f64,
    pub trail_minus_actual_net_usd: f64,
    pub trail_minus_soft_net_usd: f64,
}

/// One causal policy result for one resolved extended lifecycle.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortPostSoftTrailPolicy {
    pub status: String,
    pub trigger_timestamp_ms: Option<u64>,
    pub estimated_exit_price: f64,
    pub estimated_net_pnl_usd: f64,
    pub trail_minus_actual_net_usd: f64,
    pub trail_minus_soft_net_usd: f64,
}

/// Frozen-policy results joined to one authoritative lifecycle.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortPostSoftTrailResult {
    pub lifecycle_id: String,
    pub symbol: String,
    pub strategy_id: String,
    pub side: String,
    pub completed_post_soft_bars: usize,
    pub actual_net_pnl_usd: f64,
    pub estimated_soft_net_pnl_usd: f64,
    pub policies: BTreeMap<u16, CohortPostSoftTrailPolicy>,
}

/// Complete execution-incapable post-soft trail challenger report.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortPostSoftTrailEvidence {
    pub summary_by_giveback_bps: BTreeMap<u16, CohortPostSoftTrailSummary>,
    pub latest_results: Vec<CohortPostSoftTrailResult>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct PostSoftTrailEvidenceRaw {
    schema_version: u64,
    mode: String,
    contract: TrailContractRaw,
    policies_giveback_bps: Vec<f64>,
    summary_by_giveback_bps: BTreeMap<String, TrailSummaryRaw>,
    latest_results: Vec<TrailResultRaw>,
}

#[derive(Debug, Deserialize)]
struct TrailContractRaw {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct TrailSummaryRaw {
    eligible_extension_lifecycles: usize,
    triggered: usize,
    not_triggered: usize,
    estimated_net_pnl_usd: f64,
    actual_net_pnl_usd: f64,
    estimated_soft_net_pnl_usd: f64,
    trail_minus_actual_net_usd: f64,
    trail_minus_soft_net_usd: f64,
}

#[derive(Debug, Deserialize)]
struct TrailResultRaw {
    lifecycle_id: String,
    symbol: String,
    strategy_id: String,
    side: String,
    soft_deadline_timestamp_ms: u64,
    actual_exit_timestamp_ms: u64,
    completed_post_soft_bars: usize,
    actual_net_pnl_usd: f64,
    estimated_soft_net_pnl_usd: f64,
    policies: BTreeMap<String, TrailPolicyRaw>,
}

#[derive(Debug, Deserialize)]
struct TrailPolicyRaw {
    giveback_bps: f64,
    status: String,
    trigger_timestamp_ms: Option<u64>,
    trigger_reference_price: Option<f64>,
    trail_price_before_trigger: Option<f64>,
    best_completed_price_before_trigger: Option<f64>,
    estimated_exit_price: f64,
    estimated_net_pnl_usd: f64,
    trail_minus_actual_net_usd: f64,
    trail_minus_soft_net_usd: f64,
}

pub(crate) fn project_post_soft_trail(
    raw: Option<PostSoftTrailEvidenceRaw>,
) -> Result<Option<CohortPostSoftTrailEvidence>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_envelope(&raw)?;
    let summaries = project_summaries(raw.summary_by_giveback_bps)?;
    let eligible = summaries
        .get(&POLICIES[0])
        .map_or(0, |value| value.eligible);
    let results = project_results(raw.latest_results, eligible)?;
    validate_complete_window(&summaries, &results, eligible)?;
    Ok(Some(CohortPostSoftTrailEvidence {
        summary_by_giveback_bps: summaries,
        latest_results: results,
    }))
}

fn validate_envelope(raw: &PostSoftTrailEvidenceRaw) -> Result<(), String> {
    let contract = &raw.contract;
    let policies = raw
        .policies_giveback_bps
        .iter()
        .copied()
        .map(|value| value as u16)
        .collect::<Vec<_>>();
    if raw.schema_version != 1
        || raw.mode != MODE
        || policies != POLICIES
        || raw
            .policies_giveback_bps
            .iter()
            .any(|value| value.fract() != 0.0)
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
        || contract.performance_gate
        || contract.balance_gate
    {
        return Err("post-soft trail contract grants authority or changes frozen policies".into());
    }
    Ok(())
}

fn project_summaries(
    raw: BTreeMap<String, TrailSummaryRaw>,
) -> Result<BTreeMap<u16, CohortPostSoftTrailSummary>, String> {
    let keys = raw.keys().cloned().collect::<BTreeSet<_>>();
    let expected = POLICIES
        .map(|value| value.to_string())
        .into_iter()
        .collect();
    if keys != expected {
        return Err("post-soft trail summary policies are inconsistent".into());
    }
    let projected = raw
        .into_iter()
        .map(|(key, value)| Ok((policy_number(&key)?, project_summary(value)?)))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    if projected
        .values()
        .map(|value| value.eligible)
        .collect::<HashSet<_>>()
        .len()
        > 1
    {
        return Err("post-soft trail policy eligibility counts disagree".into());
    }
    Ok(projected)
}

fn project_summary(raw: TrailSummaryRaw) -> Result<CohortPostSoftTrailSummary, String> {
    let values = [
        raw.estimated_net_pnl_usd,
        raw.actual_net_pnl_usd,
        raw.estimated_soft_net_pnl_usd,
        raw.trail_minus_actual_net_usd,
        raw.trail_minus_soft_net_usd,
    ];
    if raw.triggered.checked_add(raw.not_triggered) != Some(raw.eligible_extension_lifecycles)
        || values.into_iter().any(|value| !value.is_finite())
        || !close(
            raw.estimated_net_pnl_usd - raw.actual_net_pnl_usd,
            raw.trail_minus_actual_net_usd,
        )
        || !close(
            raw.estimated_net_pnl_usd - raw.estimated_soft_net_pnl_usd,
            raw.trail_minus_soft_net_usd,
        )
    {
        return Err("post-soft trail summary economics are inconsistent".into());
    }
    Ok(CohortPostSoftTrailSummary {
        eligible: raw.eligible_extension_lifecycles,
        triggered: raw.triggered,
        not_triggered: raw.not_triggered,
        estimated_net_pnl_usd: raw.estimated_net_pnl_usd,
        actual_net_pnl_usd: raw.actual_net_pnl_usd,
        estimated_soft_net_pnl_usd: raw.estimated_soft_net_pnl_usd,
        trail_minus_actual_net_usd: raw.trail_minus_actual_net_usd,
        trail_minus_soft_net_usd: raw.trail_minus_soft_net_usd,
    })
}

fn project_results(
    raw: Vec<TrailResultRaw>,
    eligible: usize,
) -> Result<Vec<CohortPostSoftTrailResult>, String> {
    if raw.len() != eligible.min(LATEST_LIMIT) {
        return Err("post-soft trail result window is inconsistent".into());
    }
    let mut identities = HashSet::new();
    raw.into_iter()
        .map(|value| {
            if !identities.insert(value.lifecycle_id.clone()) {
                return Err("post-soft trail results contain a duplicate lifecycle".into());
            }
            project_result(value)
        })
        .collect()
}

fn project_result(raw: TrailResultRaw) -> Result<CohortPostSoftTrailResult, String> {
    validate_result_identity(&raw)?;
    let policies = project_policies(
        raw.policies,
        raw.soft_deadline_timestamp_ms,
        raw.actual_exit_timestamp_ms,
        raw.actual_net_pnl_usd,
        raw.estimated_soft_net_pnl_usd,
    )?;
    Ok(CohortPostSoftTrailResult {
        lifecycle_id: raw.lifecycle_id,
        symbol: raw.symbol,
        strategy_id: raw.strategy_id,
        side: raw.side,
        completed_post_soft_bars: raw.completed_post_soft_bars,
        actual_net_pnl_usd: raw.actual_net_pnl_usd,
        estimated_soft_net_pnl_usd: raw.estimated_soft_net_pnl_usd,
        policies,
    })
}

fn validate_result_identity(raw: &TrailResultRaw) -> Result<(), String> {
    let prefix = format!("{}:", raw.symbol);
    let economics = [raw.actual_net_pnl_usd, raw.estimated_soft_net_pnl_usd];
    if !raw.lifecycle_id.starts_with(&prefix)
        || raw.lifecycle_id[prefix.len()..]
            .parse::<u64>()
            .ok()
            .filter(|value| *value > 0)
            .is_none()
        || raw.strategy_id.trim().is_empty()
        || !matches!(raw.side.as_str(), "long" | "short")
        || raw.soft_deadline_timestamp_ms >= raw.actual_exit_timestamp_ms
        || economics.into_iter().any(|value| !value.is_finite())
    {
        return Err("post-soft trail lifecycle identity is inconsistent".into());
    }
    Ok(())
}

fn project_policies(
    raw: BTreeMap<String, TrailPolicyRaw>,
    soft_ms: u64,
    exit_ms: u64,
    actual: f64,
    soft: f64,
) -> Result<BTreeMap<u16, CohortPostSoftTrailPolicy>, String> {
    let keys = raw.keys().cloned().collect::<BTreeSet<_>>();
    let expected = POLICIES
        .map(|value| format!("{value}bps"))
        .into_iter()
        .collect();
    if keys != expected {
        return Err("post-soft trail lifecycle policies are inconsistent".into());
    }
    raw.into_iter()
        .map(|(key, value)| {
            let policy = policy_number(key.trim_end_matches("bps"))?;
            Ok((
                policy,
                project_policy(value, policy, soft_ms, exit_ms, actual, soft)?,
            ))
        })
        .collect()
}

fn project_policy(
    raw: TrailPolicyRaw,
    policy: u16,
    soft_ms: u64,
    exit_ms: u64,
    actual: f64,
    soft: f64,
) -> Result<CohortPostSoftTrailPolicy, String> {
    validate_policy_economics(&raw, policy, actual, soft)?;
    let status = match raw.status.as_str() {
        "triggered" => {
            validate_trigger(&raw, soft_ms, exit_ms)?;
            "triggered"
        }
        "not_triggered_before_actual_exit" => {
            validate_absent_trigger(&raw)?;
            "not_triggered"
        }
        _ => return Err("post-soft trail policy status is unsupported".into()),
    };
    Ok(CohortPostSoftTrailPolicy {
        status: status.into(),
        trigger_timestamp_ms: raw.trigger_timestamp_ms,
        estimated_exit_price: raw.estimated_exit_price,
        estimated_net_pnl_usd: raw.estimated_net_pnl_usd,
        trail_minus_actual_net_usd: raw.trail_minus_actual_net_usd,
        trail_minus_soft_net_usd: raw.trail_minus_soft_net_usd,
    })
}

fn validate_policy_economics(
    raw: &TrailPolicyRaw,
    policy: u16,
    actual: f64,
    soft: f64,
) -> Result<(), String> {
    let values = [
        raw.giveback_bps,
        raw.estimated_exit_price,
        raw.estimated_net_pnl_usd,
        raw.trail_minus_actual_net_usd,
        raw.trail_minus_soft_net_usd,
    ];
    if raw.giveback_bps != f64::from(policy)
        || raw.estimated_exit_price <= 0.0
        || values.into_iter().any(|value| !value.is_finite())
        || !close(
            raw.estimated_net_pnl_usd - actual,
            raw.trail_minus_actual_net_usd,
        )
        || !close(
            raw.estimated_net_pnl_usd - soft,
            raw.trail_minus_soft_net_usd,
        )
    {
        return Err("post-soft trail policy economics are inconsistent".into());
    }
    Ok(())
}

fn validate_trigger(raw: &TrailPolicyRaw, soft_ms: u64, exit_ms: u64) -> Result<(), String> {
    let prices = [
        raw.trigger_reference_price,
        raw.trail_price_before_trigger,
        raw.best_completed_price_before_trigger,
    ];
    if raw
        .trigger_timestamp_ms
        .is_none_or(|value| value < soft_ms || value >= exit_ms)
        || prices
            .into_iter()
            .any(|value| value.is_none_or(|price| !price.is_finite() || price <= 0.0))
    {
        return Err("post-soft trail trigger evidence is inconsistent".into());
    }
    Ok(())
}

fn validate_absent_trigger(raw: &TrailPolicyRaw) -> Result<(), String> {
    if raw.trigger_timestamp_ms.is_some()
        || raw.trigger_reference_price.is_some()
        || raw.trail_price_before_trigger.is_some()
        || raw.best_completed_price_before_trigger.is_some()
        || !close(raw.trail_minus_actual_net_usd, 0.0)
    {
        return Err("post-soft untriggered policy contains trigger evidence".into());
    }
    Ok(())
}

fn validate_complete_window(
    summaries: &BTreeMap<u16, CohortPostSoftTrailSummary>,
    results: &[CohortPostSoftTrailResult],
    eligible: usize,
) -> Result<(), String> {
    if eligible > LATEST_LIMIT {
        return Ok(());
    }
    let actual: f64 = results.iter().map(|row| row.actual_net_pnl_usd).sum();
    let soft: f64 = results
        .iter()
        .map(|row| row.estimated_soft_net_pnl_usd)
        .sum();
    for policy in POLICIES {
        let summary = &summaries[&policy];
        let values = results.iter().map(|row| &row.policies[&policy]);
        let triggered = values
            .clone()
            .filter(|value| value.status == "triggered")
            .count();
        let estimated: f64 = values.map(|value| value.estimated_net_pnl_usd).sum();
        if triggered != summary.triggered
            || !close(estimated, summary.estimated_net_pnl_usd)
            || !close(actual, summary.actual_net_pnl_usd)
            || !close(soft, summary.estimated_soft_net_pnl_usd)
        {
            return Err("post-soft trail latest results disagree with summary".into());
        }
    }
    Ok(())
}

fn policy_number(value: &str) -> Result<u16, String> {
    value
        .parse::<u16>()
        .ok()
        .filter(|value| POLICIES.contains(value))
        .ok_or_else(|| "post-soft trail policy identity is invalid".into())
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= MONEY_TOLERANCE
}
