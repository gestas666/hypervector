//! Strict projection of the frozen ETH eligible-policy forward journal.

use serde::Deserialize;

const SOURCE_STRATEGY: &str = "eth_breakout_precompression_pullback_bidirectional_v1";
const CANDIDATE_STRATEGY: &str = "eth_breakout_precompression_pullback_bidirectional_v1_v12";

/// Bounded report-only evidence for the exact ETH stop/hold candidate.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortEligiblePolicyForward {
    pub state: String,
    pub symbol: String,
    pub eligible_signals: usize,
    pub selected_non_overlapping: usize,
    pub resolved: usize,
    pub pending: usize,
    pub missing_data: usize,
    pub wins: usize,
    pub losses: usize,
    pub total_estimated_net_before_funding_bps: f64,
    pub profit_factor_before_funding: Option<f64>,
    pub funding_included: bool,
    pub total_estimated_net_after_funding_bps: Option<f64>,
    pub profit_factor_after_funding: Option<f64>,
    pub deployable: usize,
    pub portfolio_attempts: usize,
    pub latest_portfolio_classification: Option<String>,
    pub latest_attempt: Option<CohortEligiblePolicyAttempt>,
}

/// Latest pending exact-policy signal path without an assumed fill.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortEligiblePolicyAttempt {
    pub source_run_id: String,
    pub side: String,
    pub decision_time_ms: u64,
    pub status: String,
    pub reference_price: f64,
    pub observed_candles: Option<usize>,
    pub remaining_ms: Option<u64>,
    pub current_gross_return_bps: Option<f64>,
    pub current_estimated_net_before_funding_bps: Option<f64>,
    pub current_estimated_net_after_funding_bps: Option<f64>,
    pub funding_bps: Option<f64>,
    pub mfe_bps: Option<f64>,
    pub mae_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct EligiblePolicyForwardRaw {
    schema_version: u64,
    mode: String,
    state: String,
    contract: EligiblePolicyContractRaw,
    summary: EligiblePolicySummaryRaw,
    latest_attempts: Vec<EligiblePolicyAttemptRaw>,
    portfolio_journal: EligiblePolicyPortfolioRaw,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyContractRaw {
    report_only: bool,
    execution_authority: String,
    live_strategy_changed: bool,
    automatic_promotion: bool,
    portfolio_pnl_claimed: bool,
    source_strategy_id: String,
    candidate_strategy_id: String,
    symbol: String,
    source_run_id: String,
    cutoff_time_ms: u64,
    stop_bps: f64,
    maximum_hold_minutes: usize,
    modeled_round_trip_friction_bps: f64,
    funding_included: bool,
    #[serde(default)]
    funding_source: Option<String>,
    notional_usd: f64,
    one_position_per_coin: bool,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicySummaryRaw {
    eligible_signals: usize,
    selected_non_overlapping: usize,
    overlapping_excluded: usize,
    resolved: usize,
    pending: usize,
    missing_data: usize,
    wins: usize,
    losses: usize,
    total_estimated_net_before_funding_bps: f64,
    profit_factor_before_funding: Option<f64>,
    #[serde(default)]
    total_estimated_net_after_funding_bps: Option<f64>,
    #[serde(default)]
    profit_factor_after_funding: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyAttemptRaw {
    source_run_id: String,
    strategy_id: String,
    candidate_strategy_id: String,
    symbol: String,
    side: String,
    decision_time_ms: u64,
    available_time_ms: u64,
    reference_price: f64,
    status: String,
    #[serde(default)]
    observed_candles: Option<usize>,
    #[serde(default)]
    remaining_ms: Option<u64>,
    #[serde(default)]
    current_gross_return_bps: Option<f64>,
    #[serde(default)]
    current_estimated_net_before_funding_bps: Option<f64>,
    #[serde(default)]
    current_estimated_net_after_funding_bps: Option<f64>,
    #[serde(default)]
    funding_bps: Option<f64>,
    #[serde(default)]
    mfe_bps: Option<f64>,
    #[serde(default)]
    mae_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyPortfolioRaw {
    contract: EligiblePolicyPortfolioContractRaw,
    summary: EligiblePolicyPortfolioSummaryRaw,
    latest_attempts: Vec<EligiblePolicyPortfolioAttemptRaw>,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyPortfolioContractRaw {
    report_only: bool,
    execution_authority: String,
    source_strategy_id: String,
    candidate_strategy_id: String,
    symbol: String,
    position_policy: String,
    maximum_positions: usize,
    portfolio_pnl_claimed: bool,
    simulated_outcomes_are_non_additive: bool,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyPortfolioSummaryRaw {
    attempts: usize,
    deployable: usize,
    resolved: usize,
    pending: usize,
}

#[derive(Debug, Deserialize)]
struct EligiblePolicyPortfolioAttemptRaw {
    portfolio_classification: String,
}

pub(crate) fn project_eligible_policy_forward(
    raw: Option<EligiblePolicyForwardRaw>,
) -> Result<Option<CohortEligiblePolicyForward>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate(&raw)?;
    let latest_attempt = raw.latest_attempts.last().map(project_attempt);
    let latest_portfolio_classification = raw
        .portfolio_journal
        .latest_attempts
        .last()
        .map(|row| row.portfolio_classification.clone());
    Ok(Some(CohortEligiblePolicyForward {
        state: raw.state,
        symbol: raw.contract.symbol,
        eligible_signals: raw.summary.eligible_signals,
        selected_non_overlapping: raw.summary.selected_non_overlapping,
        resolved: raw.summary.resolved,
        pending: raw.summary.pending,
        missing_data: raw.summary.missing_data,
        wins: raw.summary.wins,
        losses: raw.summary.losses,
        total_estimated_net_before_funding_bps: raw.summary.total_estimated_net_before_funding_bps,
        profit_factor_before_funding: raw.summary.profit_factor_before_funding,
        funding_included: raw.contract.funding_included,
        total_estimated_net_after_funding_bps: raw.summary.total_estimated_net_after_funding_bps,
        profit_factor_after_funding: raw.summary.profit_factor_after_funding,
        deployable: raw.portfolio_journal.summary.deployable,
        portfolio_attempts: raw.portfolio_journal.summary.attempts,
        latest_portfolio_classification,
        latest_attempt,
    }))
}

fn project_attempt(raw: &EligiblePolicyAttemptRaw) -> CohortEligiblePolicyAttempt {
    CohortEligiblePolicyAttempt {
        source_run_id: raw.source_run_id.clone(),
        side: raw.side.clone(),
        decision_time_ms: raw.decision_time_ms,
        status: raw.status.clone(),
        reference_price: raw.reference_price,
        observed_candles: raw.observed_candles,
        remaining_ms: raw.remaining_ms,
        current_gross_return_bps: raw.current_gross_return_bps,
        current_estimated_net_before_funding_bps: raw.current_estimated_net_before_funding_bps,
        current_estimated_net_after_funding_bps: raw.current_estimated_net_after_funding_bps,
        funding_bps: raw.funding_bps,
        mfe_bps: raw.mfe_bps,
        mae_bps: raw.mae_bps,
    }
}

fn validate(raw: &EligiblePolicyForwardRaw) -> Result<(), String> {
    if raw.schema_version != 1
        || raw.mode != "cohort_eligible_policy_forward_report"
        || raw.limitations.is_empty()
        || raw.limitations.iter().any(|value| value.trim().is_empty())
        || !contract_valid(&raw.contract)
        || !summary_valid(&raw.summary, raw.contract.funding_included)
        || raw.latest_attempts.len() > raw.summary.selected_non_overlapping.min(100)
        || !portfolio_valid(&raw.portfolio_journal)
        || raw
            .latest_attempts
            .iter()
            .any(|attempt| !attempt_valid(attempt, &raw.contract))
        || !state_valid(&raw.state, &raw.summary)
    {
        return Err("eligible-policy forward evidence is inconsistent".into());
    }
    Ok(())
}

fn contract_valid(value: &EligiblePolicyContractRaw) -> bool {
    value.report_only
        && value.execution_authority == "none"
        && !value.live_strategy_changed
        && !value.automatic_promotion
        && !value.portfolio_pnl_claimed
        && value.source_strategy_id == SOURCE_STRATEGY
        && value.candidate_strategy_id == CANDIDATE_STRATEGY
        && value.symbol == "ETH"
        && !value.source_run_id.trim().is_empty()
        && value.cutoff_time_ms > 0
        && value.stop_bps == 60.0
        && value.maximum_hold_minutes == 720
        && value.modeled_round_trip_friction_bps == 13.0
        && funding_contract_valid(value)
        && value.notional_usd == 25.0
        && value.one_position_per_coin
}

fn funding_contract_valid(value: &EligiblePolicyContractRaw) -> bool {
    matches!(
        (value.funding_included, value.funding_source.as_deref()),
        (false, None) | (true, Some("hl_funding_history"))
    )
}

fn summary_valid(value: &EligiblePolicySummaryRaw, funding_included: bool) -> bool {
    let after_funding_valid = if funding_included && value.resolved > 0 {
        value
            .total_estimated_net_after_funding_bps
            .is_some_and(f64::is_finite)
            && value
                .profit_factor_after_funding
                .is_none_or(|number| number.is_finite() && number >= 0.0)
    } else {
        value.total_estimated_net_after_funding_bps.is_none()
            && value.profit_factor_after_funding.is_none()
    };
    value.eligible_signals == value.selected_non_overlapping + value.overlapping_excluded
        && value.selected_non_overlapping == value.resolved + value.pending + value.missing_data
        && value.wins + value.losses <= value.resolved
        && value.total_estimated_net_before_funding_bps.is_finite()
        && value
            .profit_factor_before_funding
            .is_none_or(|number| number.is_finite() && number >= 0.0)
        && after_funding_valid
}

fn portfolio_valid(value: &EligiblePolicyPortfolioRaw) -> bool {
    let contract = &value.contract;
    let summary = &value.summary;
    contract.report_only
        && contract.execution_authority == "none"
        && contract.source_strategy_id == SOURCE_STRATEGY
        && contract.candidate_strategy_id == CANDIDATE_STRATEGY
        && contract.symbol == "ETH"
        && contract.position_policy == "flat_entry_only"
        && contract.maximum_positions > 0
        && !contract.portfolio_pnl_claimed
        && contract.simulated_outcomes_are_non_additive
        && summary.deployable <= summary.attempts
        && summary.attempts == summary.resolved + summary.pending
        && value.latest_attempts.len() <= summary.attempts.min(100)
}

fn attempt_valid(value: &EligiblePolicyAttemptRaw, contract: &EligiblePolicyContractRaw) -> bool {
    let identity_valid = value.source_run_id == contract.source_run_id
        && value.strategy_id == contract.source_strategy_id
        && value.candidate_strategy_id == contract.candidate_strategy_id
        && value.symbol == contract.symbol
        && matches!(value.side.as_str(), "long" | "short")
        && value.decision_time_ms >= contract.cutoff_time_ms
        && value.available_time_ms >= value.decision_time_ms
        && value.reference_price.is_finite()
        && value.reference_price > 0.0;
    identity_valid && attempt_shape_valid(value, contract.funding_included)
}

fn attempt_shape_valid(value: &EligiblePolicyAttemptRaw, funding_included: bool) -> bool {
    let path = (
        value.observed_candles,
        value.remaining_ms,
        value.current_gross_return_bps,
        value.current_estimated_net_before_funding_bps,
        value.mfe_bps,
        value.mae_bps,
    );
    match value.status.as_str() {
        "exit_pending" => pending_path_valid(value, path, funding_included),
        "resolved" | "missing_data" => {
            path == (None, None, None, None, None, None)
                && value.funding_bps.is_none()
                && value.current_estimated_net_after_funding_bps.is_none()
        }
        _ => false,
    }
}

type PendingPath = (
    Option<usize>,
    Option<u64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    Option<f64>,
);

fn pending_path_valid(
    value: &EligiblePolicyAttemptRaw,
    path: PendingPath,
    funding_included: bool,
) -> bool {
    let (Some(bars), Some(_), Some(gross), Some(before), Some(mfe), Some(mae)) = path else {
        return false;
    };
    let base_valid = bars > 0
        && [gross, before, mfe, mae].into_iter().all(f64::is_finite)
        && mfe >= 0.0
        && mae <= 0.0;
    let funding_valid = match (
        funding_included,
        value.funding_bps,
        value.current_estimated_net_after_funding_bps,
    ) {
        (false, None, None) => true,
        (true, Some(funding), Some(after)) => {
            funding.is_finite() && after.is_finite() && (after - before - funding).abs() < 1e-6
        }
        _ => false,
    };
    base_valid && funding_valid
}

fn state_valid(state: &str, summary: &EligiblePolicySummaryRaw) -> bool {
    match state {
        "awaiting_fresh_eligible_signal" => summary.eligible_signals == 0,
        "awaiting_exact_policy_resolution" => summary.pending > 0,
        "technical_evidence_incomplete" => summary.missing_data > 0,
        "descriptive_resolved_forward_evidence" => summary.resolved > 0,
        _ => false,
    }
}
