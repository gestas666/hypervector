//! Strict projection for untuned forward-entry regime context.

use std::collections::BTreeMap;

use serde::Deserialize;

/// Outcome summary for one five-minute directional stance.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortForwardRegimeBucket {
    pub resolved: usize,
    pub wins: usize,
    pub losses: usize,
    pub total_net_return_bps: f64,
    pub profit_factor: Option<f64>,
}

/// Report-only five-minute context attached to a frozen forward experiment.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardEntryContextSummary {
    pub state_5m_observed: usize,
    pub state_5m_missing: usize,
    pub aligned: CohortForwardRegimeBucket,
    pub opposed: CohortForwardRegimeBucket,
    pub neutral: CohortForwardRegimeBucket,
    pub unavailable: CohortForwardRegimeBucket,
}

/// Report-only fifteen-minute context attached to a frozen forward experiment.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortForwardContext15mSummary {
    pub context_15m_observed: usize,
    pub context_15m_missing: usize,
    pub aligned: CohortForwardRegimeBucket,
    pub opposed: CohortForwardRegimeBucket,
    pub neutral: CohortForwardRegimeBucket,
    pub unavailable: CohortForwardRegimeBucket,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardEntryContextRaw {
    mode: String,
    execution_authority: String,
    performance_gate: bool,
    coverage: ForwardEntryContextCoverageRaw,
    by_directional_stance: ForwardDirectionalStancesRaw,
    by_state_5m: BTreeMap<String, ForwardRegimeBucketRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ForwardContext15mRaw {
    mode: String,
    execution_authority: String,
    performance_gate: bool,
    coverage: ForwardContext15mCoverageRaw,
    by_directional_stance: ForwardDirectionalStancesRaw,
    by_state_15m: BTreeMap<String, ForwardRegimeBucketRaw>,
}

#[derive(Debug, Deserialize)]
struct ForwardEntryContextCoverageRaw {
    resolved: usize,
    state_5m_observed: usize,
    state_5m_missing: usize,
}

#[derive(Debug, Deserialize)]
struct ForwardContext15mCoverageRaw {
    resolved: usize,
    context_15m_observed: usize,
    context_15m_missing: usize,
}

#[derive(Debug, Deserialize)]
struct ForwardDirectionalStancesRaw {
    aligned: ForwardRegimeBucketRaw,
    opposed: ForwardRegimeBucketRaw,
    neutral: ForwardRegimeBucketRaw,
    unavailable: ForwardRegimeBucketRaw,
}

#[derive(Debug, Deserialize)]
struct ForwardRegimeBucketRaw {
    resolved: usize,
    wins: usize,
    losses: usize,
    total_net_return_bps: f64,
    mean_net_return_bps: Option<f64>,
    profit_factor: Option<f64>,
}

pub(crate) fn project_forward_entry_context(
    raw: Option<ForwardEntryContextRaw>,
    expected_resolved: usize,
    expected_total_bps: f64,
) -> Result<Option<CohortForwardEntryContextSummary>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate(&raw, expected_resolved, expected_total_bps)?;
    let stances = raw.by_directional_stance;
    Ok(Some(CohortForwardEntryContextSummary {
        state_5m_observed: raw.coverage.state_5m_observed,
        state_5m_missing: raw.coverage.state_5m_missing,
        aligned: project_bucket(stances.aligned),
        opposed: project_bucket(stances.opposed),
        neutral: project_bucket(stances.neutral),
        unavailable: project_bucket(stances.unavailable),
    }))
}

pub(crate) fn project_forward_context_15m(
    raw: Option<ForwardContext15mRaw>,
    expected_resolved: usize,
    expected_total_bps: f64,
) -> Result<Option<CohortForwardContext15mSummary>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_context(
        &raw.mode,
        &raw.execution_authority,
        raw.performance_gate,
        raw.coverage.resolved,
        raw.coverage.context_15m_observed,
        raw.coverage.context_15m_missing,
        &raw.by_directional_stance,
        &raw.by_state_15m,
        "untuned_fifteen_minute_regime_context",
        expected_resolved,
        expected_total_bps,
    )?;
    let stances = raw.by_directional_stance;
    Ok(Some(CohortForwardContext15mSummary {
        context_15m_observed: raw.coverage.context_15m_observed,
        context_15m_missing: raw.coverage.context_15m_missing,
        aligned: project_bucket(stances.aligned),
        opposed: project_bucket(stances.opposed),
        neutral: project_bucket(stances.neutral),
        unavailable: project_bucket(stances.unavailable),
    }))
}

fn validate(
    raw: &ForwardEntryContextRaw,
    expected_resolved: usize,
    expected_total_bps: f64,
) -> Result<(), String> {
    validate_context(
        &raw.mode,
        &raw.execution_authority,
        raw.performance_gate,
        raw.coverage.resolved,
        raw.coverage.state_5m_observed,
        raw.coverage.state_5m_missing,
        &raw.by_directional_stance,
        &raw.by_state_5m,
        "untuned_five_minute_regime_context",
        expected_resolved,
        expected_total_bps,
    )
}

#[allow(clippy::too_many_arguments)]
fn validate_context(
    mode: &str,
    execution_authority: &str,
    performance_gate: bool,
    resolved: usize,
    observed: usize,
    missing: usize,
    stances: &ForwardDirectionalStancesRaw,
    states: &BTreeMap<String, ForwardRegimeBucketRaw>,
    expected_mode: &str,
    expected_resolved: usize,
    expected_total_bps: f64,
) -> Result<(), String> {
    let stance_rows = [&stances.aligned, &stances.opposed, &stances.neutral];
    let all_stances = [
        &stances.aligned,
        &stances.opposed,
        &stances.neutral,
        &stances.unavailable,
    ];
    let allowed = ["BREAKOUT", "RANGE", "TRANSITION", "TREND_DOWN", "TREND_UP"];
    let state_rows_valid = states
        .iter()
        .all(|(state, bucket)| allowed.contains(&state.as_str()) && bucket_valid(bucket));
    let observed_from_states = states.values().map(|row| row.resolved).sum::<usize>();
    let observed_from_stances = stance_rows.iter().map(|row| row.resolved).sum::<usize>();
    let total = all_stances
        .iter()
        .map(|row| row.total_net_return_bps)
        .sum::<f64>();
    if mode != expected_mode
        || execution_authority != "none"
        || performance_gate
        || resolved != expected_resolved
        || observed + missing != expected_resolved
        || observed_from_states != observed
        || observed_from_stances != observed
        || stances.unavailable.resolved != missing
        || !all_stances.iter().all(|row| bucket_valid(row))
        || !state_rows_valid
        || (total - expected_total_bps).abs() > 1e-8
    {
        return Err("forward entry regime context is inconsistent".into());
    }
    Ok(())
}

fn bucket_valid(raw: &ForwardRegimeBucketRaw) -> bool {
    let expected_mean =
        (raw.resolved > 0).then_some(raw.total_net_return_bps / raw.resolved as f64);
    raw.wins + raw.losses <= raw.resolved
        && raw.total_net_return_bps.is_finite()
        && raw
            .profit_factor
            .is_none_or(|value| value.is_finite() && value >= 0.0)
        && matches!(
            (raw.mean_net_return_bps, expected_mean),
            (None, None) | (Some(_), Some(_))
        )
        && raw.mean_net_return_bps.is_none_or(|value| {
            expected_mean.is_some_and(|expected| (value - expected).abs() <= 1e-8)
        })
}

fn project_bucket(raw: ForwardRegimeBucketRaw) -> CohortForwardRegimeBucket {
    CohortForwardRegimeBucket {
        resolved: raw.resolved,
        wins: raw.wins,
        losses: raw.losses,
        total_net_return_bps: raw.total_net_return_bps,
        profit_factor: raw.profit_factor,
    }
}
