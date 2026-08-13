//! Validation helpers for report-only forward execution and payoff evidence.

use std::collections::BTreeSet;

use chrono::DateTime;

use crate::backend_cohort_forward_challenger::{
    ForwardExecutionContract, ForwardExecutionRaw, ForwardOneBlockerChallengerRaw,
    ForwardPayoffGeometryRaw,
};

const ALIGNED_BREAKOUT_CUTOFF_MS: u64 = 1_786_054_080_000;
const ALIGNED_BREAKOUT_CONTEXT_AGE_MS: u64 = 30_000;
const ALIGNED_BREAKOUT_ENTRY_DELAY_MS: u64 = 60_000;
const ALIGNED_BREAKOUT_EXIT_DELAY_MS: u64 = 30_000;
const ALIGNED_BREAKOUT_NOTIONAL_USD: f64 = 75.0;
const ALIGNED_BREAKOUT_TAKER_FEE_RATE: f64 = 0.000_432;
const ALIGNED_BREAKOUT_STOP_BPS: f64 = 80.0;

pub(crate) fn validate_forward_challenger(
    raw: &ForwardOneBlockerChallengerRaw,
) -> Result<(), String> {
    let contract = &raw.contract;
    let execution = &contract.execution;
    let cutoff = DateTime::parse_from_rfc3339(&contract.cutoff_utc)
        .map_err(|error| format!("invalid forward challenger cutoff: {error}"))?;
    let generated = DateTime::parse_from_rfc3339(&raw.generated_at_utc)
        .map_err(|error| format!("invalid forward challenger timestamp: {error}"))?;
    if !forward_envelope_valid(raw, &cutoff, &generated)
        || !forward_execution_contract_valid(raw)
        || !forward_summary_valid(raw)
        || !payoff_geometry_valid(raw.payoff_geometry.as_ref(), execution)
    {
        return Err("forward opportunity challenger evidence is inconsistent".into());
    }
    validate_forward_executions(
        &raw.latest_executions,
        contract.cutoff_time_ms,
        execution.target_proxy_bps,
    )
}

fn forward_envelope_valid(
    raw: &ForwardOneBlockerChallengerRaw,
    cutoff: &DateTime<chrono::FixedOffset>,
    generated: &DateTime<chrono::FixedOffset>,
) -> bool {
    let expected_state = match (
        raw.coverage.exact_candidates,
        raw.coverage.resolved_executions,
    ) {
        (0, 0) => "awaiting_fresh_post_cutoff_candidate",
        (_, 0) => "awaiting_executable_resolution",
        _ => "descriptive_resolved_forward_evidence",
    };
    let contract = &raw.contract;
    let scope = contract
        .direction_scope
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    raw.schema_version == 1
        && raw.mode == "cohort_forward_one_blocker_challenger"
        && raw.state == expected_state
        && contract.report_only
        && contract.execution_authority == "none"
        && !contract.live_strategy_changed
        && !contract.automatic_promotion
        && !contract.portfolio_pnl_claimed
        && scope == BTreeSet::from(["long", "short"])
        && contract.direction_scope.len() == 2
        && cutoff.timestamp_millis() >= 0
        && cutoff.timestamp_millis() as u64 == contract.cutoff_time_ms
        && generated >= cutoff
        && !raw.falsifiers.is_empty()
        && !raw.limitations.is_empty()
}

fn forward_execution_contract_valid(raw: &ForwardOneBlockerChallengerRaw) -> bool {
    let contract = &raw.contract;
    let execution = &contract.execution;
    let Some(expected_opi) = expected_forward_opi(raw) else {
        return false;
    };
    execution.minimum_available_time_ms == contract.cutoff_time_ms
        && execution.execution_authority == "none"
        && execution.opi_cohort == expected_opi
        && execution.horizon_minutes == 60
        && execution.minimum_entry_spacing_minutes == 75
        && positive_finite(execution.notional_usd)
        && positive_finite(execution.stop_proxy_bps)
        && execution.target_proxy_bps.is_none_or(positive_finite)
        && execution.taker_fee_rate.is_finite()
        && (0.0..0.01).contains(&execution.taker_fee_rate)
        && aligned_breakout_contract_valid(raw)
}

fn aligned_breakout_contract_valid(raw: &ForwardOneBlockerChallengerRaw) -> bool {
    let execution = &raw.contract.execution;
    let candidate = raw
        .portfolio_journal
        .as_ref()
        .map(|journal| journal.contract.candidate_strategy_id.as_str());
    if !matches!(
        candidate,
        Some(
            "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
                | "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
        )
    ) {
        return true;
    }
    raw.contract.cutoff_time_ms == ALIGNED_BREAKOUT_CUTOFF_MS
        && execution.minimum_available_time_ms == ALIGNED_BREAKOUT_CUTOFF_MS
        && execution.horizon_minutes == 60
        && execution.maximum_context_age_ms == Some(ALIGNED_BREAKOUT_CONTEXT_AGE_MS)
        && execution.maximum_entry_delay_ms == Some(ALIGNED_BREAKOUT_ENTRY_DELAY_MS)
        && execution.maximum_exit_delay_ms == Some(ALIGNED_BREAKOUT_EXIT_DELAY_MS)
        && execution.minimum_entry_spacing_minutes == 75
        && approximately_equal(execution.notional_usd, ALIGNED_BREAKOUT_NOTIONAL_USD)
        && approximately_equal(execution.taker_fee_rate, ALIGNED_BREAKOUT_TAKER_FEE_RATE)
        && approximately_equal(execution.stop_proxy_bps, ALIGNED_BREAKOUT_STOP_BPS)
        && execution.target_proxy_bps.is_none()
}

fn expected_forward_opi(raw: &ForwardOneBlockerChallengerRaw) -> Option<&'static str> {
    let execution = &raw.contract.execution;
    let candidate = raw
        .portfolio_journal
        .as_ref()
        .map(|journal| journal.contract.candidate_strategy_id.as_str());
    expected_forward_opi_identity(
        execution.strategy_id.as_str(),
        execution.symbol.as_str(),
        execution.blocker.as_str(),
        candidate,
    )
}

fn expected_forward_opi_identity(
    strategy_id: &str,
    symbol: &str,
    blocker: &str,
    candidate: Option<&str>,
) -> Option<&'static str> {
    match (strategy_id, symbol, blocker, candidate) {
        (
            "hype_breakout_onset_bidirectional_v1",
            "HYPE",
            "5m_not_breakout",
            Some("hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"),
        )
        | (
            "hype_breakout_onset_bidirectional_v1",
            "SOL",
            "5m_not_breakout",
            Some("sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"),
        )
        | (
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            "xyz:SPCX",
            "pivot_break_state_missing",
            Some("spcx_swing_pivot_relaxed_fixed60_bidirectional_v1"),
        )
        | (
            "hype_breakout_onset_bidirectional_v1",
            "SOL",
            "awaiting_new_5m_breakout_onset",
            Some("sol_breakout_continuation_aligned_fixed60_bidirectional_v1"),
        ) => Some("aligned"),
        (
            "hype_breakout_onset_bidirectional_v1",
            "HYPE",
            "5m_not_breakout",
            None
            | Some(
                "hype_breakout_relaxed_60m_bidirectional_v2"
                | "hype_breakout_relaxed_target20_60m_bidirectional_v3"
                | "hype_breakout_relaxed_fixed60_matched_bidirectional_v4",
            ),
        )
        | (
            "range_onset_bidirectional_v1",
            "BTC",
            "awaiting_hourly_sma_cross",
            Some("btc_structural_continuation_fixed60_bidirectional_v1"),
        )
        | (
            "hulk_expansion_bidirectional_tuned_v2",
            "BTC",
            "money_flow_not_aligned",
            Some("btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1"),
        )
        | (
            "hulk_expansion_bidirectional_tuned_v2",
            "HYPE",
            "squeeze_not_armed",
            Some("hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1"),
        )
        | (
            "hulk_expansion_bidirectional_tuned_v2",
            "SOL",
            "expansion_trigger_not_present",
            Some("sol_hulk_expansion_trigger_relaxed_fixed60_bidirectional_v1"),
        ) => Some("all"),
        (
            "range_onset_bidirectional_v1",
            "HYPE",
            "awaiting_hourly_sma_cross",
            Some("hype_range_absorption_fixed60_bidirectional_v1"),
        ) => Some("opposed"),
        (
            "range_onset_bidirectional_v1",
            "SOL",
            "awaiting_hourly_sma_cross",
            Some("sol_aligned_range_relaxed_fixed60_bidirectional_v1"),
        ) => Some("aligned"),
        _ => None,
    }
}

fn forward_summary_valid(raw: &ForwardOneBlockerChallengerRaw) -> bool {
    let coverage = &raw.coverage;
    let summary = &raw.summary;
    coverage.selected_non_overlapping <= coverage.exact_candidates
        && coverage.resolved_executions <= coverage.selected_non_overlapping
        && coverage.resolved_executions == summary.resolved
        && summary.long_resolved + summary.short_resolved == summary.resolved
        && summary_valid(
            summary.resolved,
            summary.wins,
            summary.losses,
            summary.total_net_return_bps,
            summary.mean_net_return_bps,
            summary.profit_factor,
            summary.stop_proxy_crosses,
        )
        && optional_fraction_valid(
            summary.largest_abs_contribution_fraction,
            summary.resolved,
            summary.wins,
            summary.losses,
        )
        && raw.latest_executions.len() <= summary.resolved.min(100)
}

fn positive_finite(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

pub(crate) fn payoff_geometry_valid(
    value: Option<&ForwardPayoffGeometryRaw>,
    execution: &ForwardExecutionContract,
) -> bool {
    let (Some(value), Some(target)) = (value, execution.target_proxy_bps) else {
        return value.is_none() && execution.target_proxy_bps.is_none();
    };
    let fee = execution.taker_fee_rate * 20_000.0;
    let target_net = target - fee;
    let stop_net = -execution.stop_proxy_bps - fee;
    let break_even = (target_net > 0.0).then_some(-stop_net / (target_net - stop_net) * 100.0);
    value.scope == "binary_target_stop_benchmark_before_funding"
        && value.execution_authority == "none"
        && !value.performance_gate
        && value.fixed_horizon_changes_realized_distribution
        && approximately_equal(value.target_proxy_bps, target)
        && approximately_equal(value.stop_proxy_bps, execution.stop_proxy_bps)
        && approximately_equal(value.estimated_round_trip_fee_bps, fee)
        && approximately_equal(value.estimated_target_net_bps, target_net)
        && approximately_equal(value.estimated_stop_net_bps, stop_net)
        && optional_approximately_equal(value.break_even_target_rate_pct, break_even)
}

pub(crate) fn validate_forward_executions(
    executions: &[ForwardExecutionRaw],
    cutoff_time_ms: u64,
    target_proxy_bps: Option<f64>,
) -> Result<(), String> {
    let mut prior_exit = 0;
    for row in executions {
        if !matches!(row.side.as_str(), "long" | "short")
            || row.source_run_id.trim().is_empty()
            || row.available_time_ms < cutoff_time_ms
            || !(row.available_time_ms <= row.entry_time_ms
                && row.entry_time_ms <= row.exit_time_ms)
            || row.entry_time_ms < prior_exit
            || !execution_values_valid(row, target_proxy_bps)
        {
            return Err("forward opportunity executions are inconsistent".into());
        }
        prior_exit = row.exit_time_ms;
    }
    Ok(())
}

fn execution_values_valid(row: &ForwardExecutionRaw, target_proxy_bps: Option<f64>) -> bool {
    let values = [
        row.gross_return_bps,
        row.fee_bps,
        row.funding_bps,
        row.net_return_bps,
        row.mfe_bps,
        row.mae_bps,
    ];
    row.entry_price.is_finite()
        && row.entry_price > 0.0
        && row.exit_price.is_finite()
        && row.exit_price > 0.0
        && values.into_iter().all(f64::is_finite)
        && row.fee_bps >= 0.0
        && row.mae_bps <= row.gross_return_bps + 1e-8
        && row.gross_return_bps <= row.mfe_bps + 1e-8
        && approximately_equal(
            row.gross_return_bps - row.fee_bps + row.funding_bps,
            row.net_return_bps,
        )
        && exit_reason_valid(row, target_proxy_bps)
}

fn exit_reason_valid(row: &ForwardExecutionRaw, target_proxy_bps: Option<f64>) -> bool {
    match row.exit_reason.as_str() {
        "fixed_horizon" => !row.crossed_stop_proxy,
        "stop_proxy" => row.crossed_stop_proxy,
        "target_proxy" => {
            !row.crossed_stop_proxy
                && target_proxy_bps.is_some_and(|target| row.gross_return_bps + 1e-8 >= target)
        }
        _ => false,
    }
}

fn optional_approximately_equal(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (None, None) => true,
        (Some(left), Some(right)) => approximately_equal(left, right),
        _ => false,
    }
}

pub(crate) fn approximately_equal(left: f64, right: f64) -> bool {
    (left - right).abs() <= 1e-8
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn summary_valid(
    resolved: usize,
    wins: usize,
    losses: usize,
    total: f64,
    mean: Option<f64>,
    profit_factor: Option<f64>,
    stop_crosses: usize,
) -> bool {
    let expected_mean = (resolved > 0).then_some(total / resolved as f64);
    wins + losses <= resolved
        && stop_crosses <= resolved
        && total.is_finite()
        && (resolved > 0 || total.abs() <= 1e-9)
        && profit_factor_valid(profit_factor, losses)
        && matches!((mean, expected_mean), (None, None) | (Some(_), Some(_)))
        && mean.is_none_or(|value| {
            value.is_finite()
                && expected_mean.is_some_and(|expected| (value - expected).abs() <= 1e-8)
        })
}

#[cfg(test)]
mod tests {
    use super::expected_forward_opi_identity;

    #[test]
    fn recognizes_current_spcx_and_sol_forward_challenger_identities() {
        assert_eq!(
            expected_forward_opi_identity(
                "hip3_swing_ha_sp500_spcx_bidirectional_v2",
                "xyz:SPCX",
                "pivot_break_state_missing",
                Some("spcx_swing_pivot_relaxed_fixed60_bidirectional_v1"),
            ),
            Some("aligned")
        );
        assert_eq!(
            expected_forward_opi_identity(
                "hype_breakout_onset_bidirectional_v1",
                "SOL",
                "awaiting_new_5m_breakout_onset",
                Some("sol_breakout_continuation_aligned_fixed60_bidirectional_v1"),
            ),
            Some("aligned")
        );
    }
}

fn profit_factor_valid(value: Option<f64>, losses: usize) -> bool {
    match (value, losses) {
        (None, 0) => true,
        (Some(number), count) if count > 0 => number.is_finite() && number >= 0.0,
        _ => false,
    }
}

pub(crate) fn optional_fraction_valid(
    value: Option<f64>,
    resolved: usize,
    wins: usize,
    losses: usize,
) -> bool {
    match (value, resolved, wins + losses) {
        (None, 0, 0) | (None, _, 0) => true,
        (Some(number), count, nonzero) if count > 0 && nonzero > 0 => {
            number.is_finite() && (0.0..=1.0).contains(&number)
        }
        _ => false,
    }
}
