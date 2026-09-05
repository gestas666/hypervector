//! Strict projection of report-only candidate portfolio compatibility.

use crate::backend_cohort_forward_challenger::{
    CandidatePortfolioAttemptRaw, CandidatePortfolioContractRaw, CandidatePortfolioJournalRaw,
    CandidatePortfolioSummaryRaw, CohortCandidatePortfolioAttempt, CohortCandidatePortfolioJournal,
};

pub(crate) fn project_candidate_portfolio_journal(
    raw: Option<CandidatePortfolioJournalRaw>,
) -> Result<Option<CohortCandidatePortfolioJournal>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_journal(&raw)?;
    let latest_attempt = raw.latest_attempts.into_iter().last().map(project_attempt);
    let summary = raw.summary;
    Ok(Some(CohortCandidatePortfolioJournal {
        source_strategy_id: raw.contract.source_strategy_id,
        candidate_strategy_id: raw.contract.candidate_strategy_id,
        symbol: raw.contract.symbol,
        attempts: summary.attempts,
        deployable: summary.deployable,
        deployable_resolved: summary.deployable_resolved,
        deployable_wins: summary.deployable_wins,
        deployable_losses: summary.deployable_losses,
        deployable_total_net_return_bps: summary.deployable_total_net_return_bps,
        deployable_profit_factor: summary.deployable_profit_factor,
        deployable_largest_abs_contribution_fraction: summary
            .deployable_largest_abs_contribution_fraction,
        existing_symbol_position: summary.existing_symbol_position,
        portfolio_capacity: summary.portfolio_capacity,
        same_cycle_symbol_action: summary.same_cycle_symbol_action,
        portfolio_state_unavailable: summary.portfolio_state_unavailable,
        resolved: summary.resolved,
        pending: summary.pending,
        latest_attempt,
    }))
}

fn project_attempt(raw: CandidatePortfolioAttemptRaw) -> CohortCandidatePortfolioAttempt {
    let features = raw.entry_features;
    CohortCandidatePortfolioAttempt {
        source_run_id: raw.source_run_id,
        side: raw.side,
        decision_time_ms: raw.decision_time_ms,
        classification: raw.portfolio_classification,
        open_position_count: raw.open_position_count,
        available_position_slots: raw.available_position_slots,
        outcome_status: raw.outcome_status,
        net_return_bps: raw.net_return_bps,
        current_estimated_net_return_bps: raw.current_estimated_net_return_bps,
        mfe_bps: raw.mfe_bps,
        mae_bps: raw.mae_bps,
        remaining_ms: raw.remaining_ms,
        current_exit_top_level_capacity: raw.current_exit_top_level_capacity,
        primary_regime: features
            .as_ref()
            .and_then(|value| value.primary_regime.clone()),
        state_1m: features.as_ref().and_then(|value| value.state_1m.clone()),
        state_5m: features.as_ref().and_then(|value| value.state_5m.clone()),
        context_15m: features
            .as_ref()
            .and_then(|value| value.context_15m.clone()),
        structural_direction: features
            .as_ref()
            .and_then(|value| value.structural_direction.clone()),
        breakout_volume_ratio: features
            .as_ref()
            .and_then(|value| value.breakout_volume_ratio),
        current_bbwp_percentile: features
            .as_ref()
            .and_then(|value| value.current_bbwp_percentile),
        regime_strength: features.as_ref().and_then(|value| value.regime_strength),
        same_cycle_action_count: raw.same_cycle_symbol_actions.len(),
        same_cycle_withheld_count: raw.same_cycle_symbol_withheld.len(),
    }
}

fn validate_journal(raw: &CandidatePortfolioJournalRaw) -> Result<(), String> {
    let expected_state = if raw.summary.attempts == 0 {
        "awaiting_attempts"
    } else {
        "resolved_observations"
    };
    if raw.schema_version != 1
        || raw.mode != "candidate_portfolio_compatibility_journal"
        || raw.state != expected_state
        || !contract_valid(&raw.contract)
        || !summary_valid(&raw.summary)
        || raw.latest_attempts.len() > raw.summary.attempts.min(100)
        || raw.limitations.is_empty()
        || raw.limitations.iter().any(|value| value.trim().is_empty())
    {
        return Err("candidate portfolio journal evidence is inconsistent".into());
    }
    validate_attempts(raw)
}

fn contract_valid(contract: &CandidatePortfolioContractRaw) -> bool {
    let identity_valid = candidate_identity_valid(
        contract.source_strategy_id.as_str(),
        contract.candidate_strategy_id.as_str(),
        contract.symbol.as_str(),
    );
    contract.report_only
        && contract.execution_authority == "none"
        && identity_valid
        && contract.position_policy == "flat_entry_only"
        && contract.maximum_positions > 0
        && !contract.portfolio_pnl_claimed
        && contract.simulated_outcomes_are_non_additive
}

fn candidate_identity_valid(source: &str, candidate: &str, symbol: &str) -> bool {
    primary_candidate_identity_valid(source, candidate, symbol)
        || secondary_candidate_identity_valid(source, candidate, symbol)
}

fn primary_candidate_identity_valid(source: &str, candidate: &str, symbol: &str) -> bool {
    matches!(
        (source, candidate, symbol),
        (
            "hype_breakout_onset_bidirectional_v1",
            "hype_breakout_relaxed_60m_bidirectional_v2"
                | "hype_breakout_relaxed_target20_60m_bidirectional_v3"
                | "hype_breakout_relaxed_fixed60_matched_bidirectional_v4",
            "HYPE",
        ) | (
            "range_onset_bidirectional_v1",
            "btc_structural_continuation_fixed60_bidirectional_v1",
            "BTC",
        ) | (
            "hulk_expansion_bidirectional_tuned_v2",
            "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1",
            "HYPE",
        ) | (
            "hulk_expansion_bidirectional_tuned_v2",
            "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1",
            "BTC",
        ) | (
            "hulk_expansion_bidirectional_tuned_v2",
            "sol_hulk_expansion_trigger_relaxed_fixed60_bidirectional_v1",
            "SOL",
        ) | (
            "range_onset_bidirectional_v1",
            "hype_range_absorption_fixed60_bidirectional_v1",
            "HYPE",
        )
    )
}

fn secondary_candidate_identity_valid(source: &str, candidate: &str, symbol: &str) -> bool {
    matches!(
        (source, candidate, symbol),
        (
            "range_onset_bidirectional_v1",
            "sol_aligned_range_relaxed_fixed60_bidirectional_v1",
            "SOL",
        ) | (
            "hype_breakout_onset_bidirectional_v1",
            "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
            "HYPE",
        ) | (
            "hype_breakout_onset_bidirectional_v1",
            "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
            "SOL",
        ) | (
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            "spcx_swing_pivot_relaxed_fixed60_bidirectional_v1",
            "xyz:SPCX",
        ) | (
            "hype_breakout_onset_bidirectional_v1",
            "sol_breakout_continuation_aligned_fixed60_bidirectional_v1",
            "SOL",
        )
    )
}

fn summary_valid(summary: &CandidatePortfolioSummaryRaw) -> bool {
    summary.attempts
        == summary.deployable
            + summary.existing_symbol_position
            + summary.portfolio_capacity
            + summary.same_cycle_symbol_action
            + summary.portfolio_state_unavailable
        && summary.attempts == summary.resolved + summary.pending
        && deployable_summary_shape_valid(summary)
}

fn deployable_summary_shape_valid(summary: &CandidatePortfolioSummaryRaw) -> bool {
    let required = (
        summary.deployable_resolved,
        summary.deployable_wins,
        summary.deployable_losses,
        summary.deployable_total_net_return_bps,
    );
    match required {
        (None, None, None, None) => {
            summary.deployable_profit_factor.is_none()
                && summary
                    .deployable_largest_abs_contribution_fraction
                    .is_none()
        }
        (Some(resolved), Some(wins), Some(losses), Some(net)) => {
            resolved <= summary.deployable
                && wins + losses <= resolved
                && net.is_finite()
                && summary
                    .deployable_profit_factor
                    .is_none_or(|value| value.is_finite() && value >= 0.0)
                && summary
                    .deployable_largest_abs_contribution_fraction
                    .is_none_or(|value| value.is_finite() && (0.0..=1.0).contains(&value))
        }
        _ => false,
    }
}

fn validate_attempts(raw: &CandidatePortfolioJournalRaw) -> Result<(), String> {
    for row in &raw.latest_attempts {
        if !attempt_valid(row, raw.contract.maximum_positions) {
            return Err("candidate portfolio journal attempt is inconsistent".into());
        }
    }
    if raw.summary.attempts <= 100 && !latest_counts_reconcile(&raw.latest_attempts, &raw.summary) {
        return Err("candidate portfolio journal summary is inconsistent".into());
    }
    Ok(())
}

fn attempt_valid(row: &CandidatePortfolioAttemptRaw, maximum_positions: usize) -> bool {
    let classification = row.portfolio_classification.as_str();
    let unavailable = classification == "portfolio_state_unavailable";
    let portfolio_valid = if unavailable {
        row.open_position_count.is_none() && row.available_position_slots.is_none()
    } else {
        matches!(
            (row.open_position_count, row.available_position_slots),
            (Some(open), Some(slots)) if open + slots == maximum_positions
        )
    };
    !row.source_run_id.trim().is_empty()
        && matches!(row.side.as_str(), "long" | "short")
        && row.decision_time_ms > 0
        && classification_valid(row)
        && portfolio_valid
        && outcome_valid(row)
        && pending_path_valid(row)
        && entry_features_valid(row)
        && routes_valid(row)
}

fn entry_features_valid(row: &CandidatePortfolioAttemptRaw) -> bool {
    let Some(value) = &row.entry_features else {
        return true;
    };
    let observed = value.primary_regime.is_some()
        || value.state_1m.is_some()
        || value.state_5m.is_some()
        || value.context_15m.is_some()
        || value.structural_direction.is_some()
        || value.breakout_volume_ratio.is_some()
        || value.current_bbwp_percentile.is_some()
        || value.regime_strength.is_some();
    observed
        && regime_tuple_valid(value)
        && value
            .structural_direction
            .as_deref()
            .is_none_or(|direction| direction == row.side)
        && value
            .breakout_volume_ratio
            .is_none_or(|ratio| ratio.is_finite() && ratio >= 0.0)
        && value
            .current_bbwp_percentile
            .is_none_or(|percentile| percentile.is_finite() && (0.0..=100.0).contains(&percentile))
        && value
            .regime_strength
            .is_none_or(|strength| strength.is_finite() && (0.0..=1.0).contains(&strength))
}

fn regime_tuple_valid(
    value: &crate::backend_cohort_forward_challenger::CandidateEntryFeaturesRaw,
) -> bool {
    let states = [
        value.primary_regime.as_deref(),
        value.state_1m.as_deref(),
        value.state_5m.as_deref(),
        value.context_15m.as_deref(),
    ];
    states
        .into_iter()
        .all(|state| state.is_none_or(valid_regime_state))
        && primary_matches_state_5m(value)
}

fn primary_matches_state_5m(
    value: &crate::backend_cohort_forward_challenger::CandidateEntryFeaturesRaw,
) -> bool {
    match (value.primary_regime.as_deref(), value.state_5m.as_deref()) {
        (Some(primary), Some(state_5m)) => primary == state_5m,
        _ => true,
    }
}

fn valid_regime_state(state: &str) -> bool {
    matches!(
        state,
        "BREAKOUT" | "RANGE" | "TRANSITION" | "TREND_DOWN" | "TREND_UP"
    )
}

fn classification_valid(row: &CandidatePortfolioAttemptRaw) -> bool {
    match row.portfolio_classification.as_str() {
        "deployable_flat_entry" => {
            row.symbol_state.as_deref() == Some("FLAT")
                && row.symbol_position_side.is_none()
                && row.same_cycle_symbol_actions.is_empty()
        }
        "existing_symbol_position" => row.symbol_position_side.is_some(),
        "portfolio_capacity" => row.symbol_state.as_deref() == Some("FLAT"),
        "same_cycle_symbol_action" => !row.same_cycle_symbol_actions.is_empty(),
        "portfolio_state_unavailable" => row.symbol_state.is_none(),
        _ => false,
    }
}

fn outcome_valid(row: &CandidatePortfolioAttemptRaw) -> bool {
    match row.outcome_status.as_str() {
        "resolved" => matches!(
            (row.net_return_bps, row.simulated_net_pnl_usd),
            (Some(net), Some(pnl)) if net.is_finite() && pnl.is_finite()
        ),
        "pending_or_unresolved" => {
            row.net_return_bps.is_none() && row.simulated_net_pnl_usd.is_none()
        }
        _ => false,
    }
}

fn pending_path_valid(row: &CandidatePortfolioAttemptRaw) -> bool {
    let values = (
        row.current_estimated_net_return_bps,
        row.mfe_bps,
        row.mae_bps,
        row.remaining_ms,
        row.current_exit_top_level_capacity,
    );
    match values {
        (None, None, None, None, None) => true,
        (Some(net), Some(mfe), Some(mae), Some(_), Some(_)) => {
            row.outcome_status == "pending_or_unresolved"
                && net.is_finite()
                && mfe.is_finite()
                && mae.is_finite()
                && mfe >= mae
        }
        _ => false,
    }
}

fn routes_valid(row: &CandidatePortfolioAttemptRaw) -> bool {
    row.same_cycle_symbol_actions
        .iter()
        .all(|route| !route.strategy_id.trim().is_empty() && route.reason.is_none())
        && row.same_cycle_symbol_withheld.iter().all(|route| {
            !route.strategy_id.trim().is_empty()
                && route
                    .reason
                    .as_ref()
                    .is_some_and(|value| !value.trim().is_empty())
        })
}

fn latest_counts_reconcile(
    rows: &[CandidatePortfolioAttemptRaw],
    summary: &CandidatePortfolioSummaryRaw,
) -> bool {
    let count = |value: &str| {
        rows.iter()
            .filter(|row| row.portfolio_classification == value)
            .count()
    };
    count("deployable_flat_entry") == summary.deployable
        && count("existing_symbol_position") == summary.existing_symbol_position
        && count("portfolio_capacity") == summary.portfolio_capacity
        && count("same_cycle_symbol_action") == summary.same_cycle_symbol_action
        && count("portfolio_state_unavailable") == summary.portfolio_state_unavailable
        && rows
            .iter()
            .filter(|row| row.outcome_status == "resolved")
            .count()
            == summary.resolved
        && deployable_economics_reconcile(rows, summary)
}

fn deployable_economics_reconcile(
    rows: &[CandidatePortfolioAttemptRaw],
    summary: &CandidatePortfolioSummaryRaw,
) -> bool {
    let Some(expected_resolved) = summary.deployable_resolved else {
        return true;
    };
    let values: Vec<f64> = rows
        .iter()
        .filter(|row| {
            row.portfolio_classification == "deployable_flat_entry"
                && row.outcome_status == "resolved"
        })
        .filter_map(|row| row.net_return_bps)
        .collect();
    let gains: f64 = values.iter().copied().filter(|value| *value > 0.0).sum();
    let losses: f64 = -values
        .iter()
        .copied()
        .filter(|value| *value < 0.0)
        .sum::<f64>();
    let absolute: f64 = values.iter().map(|value| value.abs()).sum();
    let profit_factor = (losses > 0.0).then_some(gains / losses);
    let concentration = (absolute > 0.0)
        .then(|| values.iter().map(|value| value.abs()).fold(0.0, f64::max) / absolute);
    values.len() == expected_resolved
        && summary.deployable_wins == Some(values.iter().filter(|value| **value > 0.0).count())
        && summary.deployable_losses == Some(values.iter().filter(|value| **value < 0.0).count())
        && close(
            summary.deployable_total_net_return_bps,
            Some(values.iter().sum()),
        )
        && close(summary.deployable_profit_factor, profit_factor)
        && close(
            summary.deployable_largest_abs_contribution_fraction,
            concentration,
        )
}

fn close(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (None, None) => true,
        (Some(left), Some(right)) => (left - right).abs() <= 1e-9,
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::candidate_identity_valid;

    #[test]
    fn recognizes_current_spcx_and_sol_candidate_portfolio_identities() {
        assert!(candidate_identity_valid(
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            "spcx_swing_pivot_relaxed_fixed60_bidirectional_v1",
            "xyz:SPCX",
        ));
        assert!(candidate_identity_valid(
            "hype_breakout_onset_bidirectional_v1",
            "sol_breakout_continuation_aligned_fixed60_bidirectional_v1",
            "SOL",
        ));
    }
}
