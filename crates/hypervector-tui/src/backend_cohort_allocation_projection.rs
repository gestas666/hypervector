//! Raw allocation evidence validation and projection.

use std::collections::BTreeSet;

use serde::Deserialize;
use serde_json::Value;

use super::{
    CohortAllocationCapacity, CohortAllocationCapacitySide, CohortAllocationChallenger,
    CohortAllocationExecutionSample, CohortAllocationPortfolio, CohortAllocationProjection,
};
use crate::backend_cohort_risk_utilization::CohortRiskUtilization;

const MODE: &str = "cohort_selective_allocation_challenger_v1";
const TARGET: &str = "hype_breakout_onset_bidirectional_v1|HYPE";
const EPSILON: f64 = 1e-9;

#[derive(Debug, Deserialize)]
pub(crate) struct AllocationChallengerRaw {
    schema_version: u64,
    mode: String,
    status: String,
    contract: AllocationContractRaw,
    target_provider_symbol: String,
    account_value_usd: f64,
    current: AllocationProjectionRaw,
    candidate: AllocationCandidateRaw,
    portfolio: AllocationPortfolioRaw,
    required_profile_changes: ProfileChangesRaw,
    execution_sample: AllocationExecutionSampleRaw,
    #[serde(default)]
    visible_depth_capacity: Option<AllocationCapacityRaw>,
    profit_forecast: Value,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct AllocationContractRaw {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_sizing_change: bool,
    automatic_promotion: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct AllocationProjectionRaw {
    configured_leverage: f64,
    configured_margin_fraction: f64,
    configured_max_notional_usd: f64,
    uncapped_notional_usd: f64,
    planned_notional_usd: f64,
    planned_margin_usd: f64,
    effective_margin_fraction: f64,
    cap_binding: bool,
}

#[derive(Debug, Deserialize)]
struct AllocationCandidateRaw {
    #[serde(flatten)]
    projection: AllocationProjectionRaw,
    effective_change: bool,
}

#[derive(Debug, Deserialize)]
struct AllocationPortfolioRaw {
    current_maximum_margin_fraction: f64,
    candidate_maximum_margin_fraction: f64,
    change_percentage_points: f64,
}

#[derive(Debug, Deserialize)]
struct ProfileChangesRaw {
    asset: String,
    candidate_asset_ceiling_usd: f64,
    candidate_target_cap_usd: f64,
    pinned_provider_symbols: Vec<String>,
    restart_required: bool,
}

#[derive(Debug, Deserialize)]
struct AllocationExecutionSampleRaw {
    status: String,
    #[serde(default)]
    closed_trades: Option<usize>,
    #[serde(default)]
    net_pnl_usd: Option<f64>,
    #[serde(default)]
    profit_factor: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct AllocationCapacityRaw {
    status: String,
    symbol: String,
    snapshot_count: usize,
    current_notional_usd: f64,
    candidate_notional_usd: f64,
    window_start_timestamp_ms: u64,
    window_end_timestamp_ms: u64,
    contract: AllocationCapacityContractRaw,
    by_side: AllocationCapacitySidesRaw,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct AllocationCapacityContractRaw {
    report_only: bool,
    execution_authority: String,
    fills_assumed: bool,
    promotion_gate: bool,
}

#[derive(Debug, Deserialize)]
struct AllocationCapacitySidesRaw {
    long: AllocationCapacitySideRaw,
    short: AllocationCapacitySideRaw,
}

#[derive(Debug, Deserialize)]
struct AllocationCapacitySideRaw {
    complete_rate: f64,
    bbo_fill_rate: f64,
    median_impact_bps: Option<f64>,
    p95_impact_bps: Option<f64>,
    maximum_impact_bps: Option<f64>,
    minimum_bbo_notional_usd: f64,
}

pub(crate) fn project_allocation_challenger(
    raw: Option<AllocationChallengerRaw>,
    risk: Option<&CohortRiskUtilization>,
) -> Result<Option<CohortAllocationChallenger>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let risk = risk.ok_or("allocation challenger requires risk-utilization evidence")?;
    validate(&value, risk)?;
    Ok(Some(project(value)))
}

fn validate(value: &AllocationChallengerRaw, risk: &CohortRiskUtilization) -> Result<(), String> {
    validate_envelope(value)?;
    validate_projection(&value.current, value.account_value_usd)?;
    validate_projection(&value.candidate.projection, value.account_value_usd)?;
    validate_risk_binding(value, risk)?;
    validate_portfolio(value, risk)?;
    validate_profile_changes(value)?;
    validate_sample(&value.execution_sample)?;
    if let Some(capacity) = &value.visible_depth_capacity {
        validate_capacity(capacity, value)?;
    }
    Ok(())
}

fn validate_capacity(
    capacity: &AllocationCapacityRaw,
    challenger: &AllocationChallengerRaw,
) -> Result<(), String> {
    let contract = &capacity.contract;
    let limitations_valid = !capacity.limitations.is_empty()
        && capacity
            .limitations
            .iter()
            .all(|item| !item.trim().is_empty());
    let envelope_valid = capacity.status == "observed"
        && capacity.symbol == "HYPE"
        && (1..=240).contains(&capacity.snapshot_count)
        && near(
            capacity.current_notional_usd,
            challenger.current.planned_notional_usd,
        )
        && near(
            capacity.candidate_notional_usd,
            challenger.candidate.projection.planned_notional_usd,
        )
        && capacity.window_start_timestamp_ms <= capacity.window_end_timestamp_ms
        && contract.report_only
        && contract.execution_authority == "none"
        && !contract.fills_assumed
        && !contract.promotion_gate
        && limitations_valid;
    valid_or_error(envelope_valid, "allocation capacity contract is invalid")?;
    validate_capacity_side(&capacity.by_side.long)?;
    validate_capacity_side(&capacity.by_side.short)
}

fn validate_capacity_side(value: &AllocationCapacitySideRaw) -> Result<(), String> {
    let rates_valid = unit_fraction(value.complete_rate)
        && unit_fraction(value.bbo_fill_rate)
        && value.bbo_fill_rate <= value.complete_rate;
    let impact_shape_valid = match (
        value.median_impact_bps,
        value.p95_impact_bps,
        value.maximum_impact_bps,
    ) {
        (Some(median), Some(p95), Some(maximum)) if value.complete_rate > 0.0 => {
            nonnegative(median)
                && nonnegative(p95)
                && nonnegative(maximum)
                && median <= p95
                && p95 <= maximum
        }
        (None, None, None) => value.complete_rate == 0.0,
        _ => false,
    };
    valid_or_error(
        rates_valid && impact_shape_valid && positive(value.minimum_bbo_notional_usd),
        "allocation capacity side is invalid",
    )
}

fn validate_envelope(value: &AllocationChallengerRaw) -> Result<(), String> {
    let contract = &value.contract;
    let limitations_valid = !value.limitations.is_empty()
        && value.limitations.iter().all(|item| !item.trim().is_empty());
    let invalid = value.schema_version != 1
        || value.mode != MODE
        || value.status != "candidate_not_active"
        || value.target_provider_symbol != TARGET
        || !positive(value.account_value_usd)
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_sizing_change
        || contract.automatic_promotion
        || contract.performance_gate
        || contract.balance_gate
        || !value.profit_forecast.is_null()
        || !limitations_valid;
    valid_or_error(!invalid, "allocation challenger contract is invalid")
}

fn validate_projection(value: &AllocationProjectionRaw, account: f64) -> Result<(), String> {
    let expected_uncapped = account * value.configured_margin_fraction * value.configured_leverage;
    let expected_planned = expected_uncapped.min(value.configured_max_notional_usd);
    let expected_margin = expected_planned / value.configured_leverage;
    let expected_fraction = expected_margin / account;
    let positive_values = [
        value.configured_leverage,
        value.configured_margin_fraction,
        value.configured_max_notional_usd,
        value.uncapped_notional_usd,
        value.planned_notional_usd,
        value.planned_margin_usd,
        value.effective_margin_fraction,
    ]
    .into_iter()
    .all(positive);
    let valid = positive_values
        && value.configured_margin_fraction <= 1.0
        && near(value.uncapped_notional_usd, expected_uncapped)
        && near(value.planned_notional_usd, expected_planned)
        && near(value.planned_margin_usd, expected_margin)
        && near(value.effective_margin_fraction, expected_fraction)
        && value.cap_binding == (expected_uncapped > value.configured_max_notional_usd);
    valid_or_error(valid, "allocation challenger sizing is inconsistent")
}

fn validate_risk_binding(
    value: &AllocationChallengerRaw,
    risk: &CohortRiskUtilization,
) -> Result<(), String> {
    let target = risk
        .by_provider_symbol
        .get(TARGET)
        .ok_or("allocation target is missing from risk utilization")?;
    let current = &value.current;
    let sizing = &target.sizing;
    let matches = near(value.account_value_usd, risk.account_value_usd)
        && near(current.configured_leverage, sizing.configured_leverage)
        && near(
            current.configured_margin_fraction,
            sizing.configured_margin_fraction,
        )
        && near(
            current.configured_max_notional_usd,
            sizing.configured_max_notional_usd,
        )
        && near(current.planned_notional_usd, sizing.planned_notional_usd)
        && near(current.planned_margin_usd, sizing.planned_margin_usd)
        && near(
            current.effective_margin_fraction,
            sizing.effective_margin_fraction,
        )
        && current.cap_binding == sizing.cap_binding;
    valid_or_error(
        matches,
        "allocation current sizing disagrees with runtime risk",
    )
}

fn validate_portfolio(
    value: &AllocationChallengerRaw,
    risk: &CohortRiskUtilization,
) -> Result<(), String> {
    let portfolio = &value.portfolio;
    let expected_change = (portfolio.candidate_maximum_margin_fraction
        - portfolio.current_maximum_margin_fraction)
        * 100.0;
    let effective_change = !near(
        value.current.planned_notional_usd,
        value.candidate.projection.planned_notional_usd,
    );
    let valid = positive(portfolio.current_maximum_margin_fraction)
        && positive(portfolio.candidate_maximum_margin_fraction)
        && portfolio.change_percentage_points.is_finite()
        && near(
            portfolio.current_maximum_margin_fraction,
            risk.maximum_effective_margin_fraction,
        )
        && near(portfolio.change_percentage_points, expected_change)
        && value.candidate.effective_change == effective_change;
    valid_or_error(valid, "allocation portfolio comparison is inconsistent")
}

fn validate_profile_changes(value: &AllocationChallengerRaw) -> Result<(), String> {
    let changes = &value.required_profile_changes;
    let pins = changes
        .pinned_provider_symbols
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let required = BTreeSet::from([
        "hulk_expansion_bidirectional_tuned_v2|HYPE",
        "range_onset_bidirectional_v1|HYPE",
    ]);
    let valid = changes.asset == "HYPE"
        && changes.restart_required
        && near(
            changes.candidate_target_cap_usd,
            value.candidate.projection.configured_max_notional_usd,
        )
        && changes.candidate_asset_ceiling_usd >= changes.candidate_target_cap_usd
        && pins == required;
    valid_or_error(valid, "allocation profile changes are incomplete")
}

fn validate_sample(value: &AllocationExecutionSampleRaw) -> Result<(), String> {
    let valid = match value.status.as_str() {
        "no_resolved_execution_sample" => {
            value.closed_trades.is_none()
                && value.net_pnl_usd.is_none()
                && value.profit_factor.is_none()
        }
        "resolved_live_sample" => {
            value.closed_trades.is_some_and(|count| count > 0)
                && value.net_pnl_usd.is_some_and(f64::is_finite)
                && value
                    .profit_factor
                    .is_none_or(|number| number.is_finite() && number >= 0.0)
        }
        _ => false,
    };
    valid_or_error(valid, "allocation execution sample is invalid")
}

fn project(value: AllocationChallengerRaw) -> CohortAllocationChallenger {
    CohortAllocationChallenger {
        status: value.status,
        target_provider_symbol: value.target_provider_symbol,
        account_value_usd: value.account_value_usd,
        current: projection(value.current),
        candidate: projection(value.candidate.projection),
        effective_change: value.candidate.effective_change,
        portfolio: CohortAllocationPortfolio {
            current_maximum_margin_fraction: value.portfolio.current_maximum_margin_fraction,
            candidate_maximum_margin_fraction: value.portfolio.candidate_maximum_margin_fraction,
            change_percentage_points: value.portfolio.change_percentage_points,
        },
        execution_sample: CohortAllocationExecutionSample {
            status: value.execution_sample.status,
            closed_trades: value.execution_sample.closed_trades,
            net_pnl_usd: value.execution_sample.net_pnl_usd,
            profit_factor: value.execution_sample.profit_factor,
        },
        visible_depth_capacity: value.visible_depth_capacity.map(project_capacity),
    }
}

fn project_capacity(value: AllocationCapacityRaw) -> CohortAllocationCapacity {
    CohortAllocationCapacity {
        snapshot_count: value.snapshot_count,
        candidate_notional_usd: value.candidate_notional_usd,
        long: project_capacity_side(value.by_side.long),
        short: project_capacity_side(value.by_side.short),
    }
}

fn project_capacity_side(value: AllocationCapacitySideRaw) -> CohortAllocationCapacitySide {
    CohortAllocationCapacitySide {
        complete_rate: value.complete_rate,
        bbo_fill_rate: value.bbo_fill_rate,
        median_impact_bps: value.median_impact_bps,
        p95_impact_bps: value.p95_impact_bps,
        maximum_impact_bps: value.maximum_impact_bps,
        minimum_bbo_notional_usd: value.minimum_bbo_notional_usd,
    }
}

fn projection(value: AllocationProjectionRaw) -> CohortAllocationProjection {
    CohortAllocationProjection {
        configured_leverage: value.configured_leverage,
        configured_margin_fraction: value.configured_margin_fraction,
        configured_max_notional_usd: value.configured_max_notional_usd,
        uncapped_notional_usd: value.uncapped_notional_usd,
        planned_notional_usd: value.planned_notional_usd,
        planned_margin_usd: value.planned_margin_usd,
        effective_margin_fraction: value.effective_margin_fraction,
        cap_binding: value.cap_binding,
    }
}

fn valid_or_error(valid: bool, message: &str) -> Result<(), String> {
    if valid { Ok(()) } else { Err(message.into()) }
}

fn positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn unit_fraction(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

fn near(left: f64, right: f64) -> bool {
    (left - right).abs() <= EPSILON * left.abs().max(right.abs()).max(1.0)
}
