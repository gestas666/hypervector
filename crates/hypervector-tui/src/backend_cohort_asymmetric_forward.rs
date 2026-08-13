//! Strict projection of the predeclared asymmetric portfolio observer.

use chrono::DateTime;
use serde::Deserialize;
use std::collections::BTreeSet;

const MODE: &str = "cohort_asymmetric_shared_portfolio_forward_observer_v1";
const SCOPE: &str = "resolved_venue_lifecycles_entered_at_or_after_predeclared_cutoff";
const HYPOTHESIS: &str = "cohort-asymmetric-shared-portfolio";
const VARIANT: &str = "sol_symmetric_sensitivity";

#[derive(Debug, Clone, PartialEq)]
pub struct CohortAsymmetricForwardObserver {
    pub evidence_state: String,
    pub predeclared_at_utc: String,
    pub entry_cutoff_timestamp_ms: i64,
    pub candidate: CohortAsymmetricEconomics,
    pub excluded_symmetric_sides: CohortAsymmetricEconomics,
    pub source_counts: CohortAsymmetricSourceCounts,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortAsymmetricEconomics {
    pub closed_trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub breakeven: usize,
    pub net_pnl_usd: f64,
    pub fees_usd: f64,
    pub funding_usd: f64,
    pub profit_factor: Option<f64>,
    pub median_return_on_margin_pct: Option<f64>,
    pub net_pnl_excluding_largest_winner_usd: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortAsymmetricSourceCounts {
    pub candidate_post_cutoff: usize,
    pub excluded_symmetric_post_cutoff: usize,
    pub pre_cutoff_in_scope: usize,
    pub profile_mismatch_in_scope: usize,
    pub unrelated: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct AsymmetricForwardRaw {
    schema_version: u64,
    mode: String,
    scope: String,
    contract: AsymmetricContractRaw,
    hypothesis_id: String,
    selected_variant_id: String,
    current_profile_fingerprint: String,
    current_run_id: String,
    predeclared_at_utc: String,
    entry_cutoff_timestamp_ms: i64,
    candidate_route_sides: Vec<[String; 3]>,
    excluded_symmetric_route_sides: Vec<[String; 3]>,
    source_counts: AsymmetricSourceCountsRaw,
    candidate: AsymmetricEconomicsRaw,
    excluded_symmetric_sides: AsymmetricEconomicsRaw,
    evidence_state: String,
}

#[derive(Debug, Deserialize)]
struct AsymmetricContractRaw {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    automatic_promotion: bool,
    performance_gate: bool,
    balance_gate: bool,
    trade_count_gate: bool,
    actual_resolved_lifecycles_only: bool,
    counterfactual_fills_claimed: bool,
    capital_reallocation_claimed: bool,
}

#[derive(Debug, Deserialize)]
struct AsymmetricSourceCountsRaw {
    candidate_post_cutoff: usize,
    excluded_symmetric_post_cutoff: usize,
    pre_cutoff_in_scope: usize,
    profile_mismatch_in_scope: usize,
    unrelated: usize,
}

#[derive(Debug, Deserialize)]
struct AsymmetricEconomicsRaw {
    closed_trades: usize,
    wins: usize,
    losses: usize,
    breakeven: usize,
    net_pnl_usd: f64,
    fees_usd: f64,
    funding_usd: f64,
    profit_factor: Option<f64>,
    mean_return_on_margin_pct: Option<f64>,
    median_return_on_margin_pct: Option<f64>,
    largest_winner_usd: Option<f64>,
    net_pnl_excluding_largest_winner_usd: Option<f64>,
}

pub(crate) fn project_asymmetric_forward_observer(
    raw: Option<AsymmetricForwardRaw>,
) -> Result<Option<CohortAsymmetricForwardObserver>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_identity(&raw)?;
    let candidate = project_economics(raw.candidate, "candidate")?;
    let excluded = project_economics(raw.excluded_symmetric_sides, "symmetric control")?;
    if raw.source_counts.candidate_post_cutoff != candidate.closed_trades
        || raw.source_counts.excluded_symmetric_post_cutoff != excluded.closed_trades
    {
        return Err("asymmetric portfolio observer source counts do not reconcile".into());
    }
    validate_evidence_state(&raw.evidence_state, candidate.closed_trades)?;
    Ok(Some(CohortAsymmetricForwardObserver {
        evidence_state: raw.evidence_state,
        predeclared_at_utc: raw.predeclared_at_utc,
        entry_cutoff_timestamp_ms: raw.entry_cutoff_timestamp_ms,
        candidate,
        excluded_symmetric_sides: excluded,
        source_counts: CohortAsymmetricSourceCounts {
            candidate_post_cutoff: raw.source_counts.candidate_post_cutoff,
            excluded_symmetric_post_cutoff: raw.source_counts.excluded_symmetric_post_cutoff,
            pre_cutoff_in_scope: raw.source_counts.pre_cutoff_in_scope,
            profile_mismatch_in_scope: raw.source_counts.profile_mismatch_in_scope,
            unrelated: raw.source_counts.unrelated,
        },
    }))
}

fn validate_identity(raw: &AsymmetricForwardRaw) -> Result<(), String> {
    let contract = &raw.contract;
    if raw.schema_version != 1
        || raw.mode != MODE
        || raw.scope != SCOPE
        || raw.hypothesis_id != HYPOTHESIS
        || raw.selected_variant_id != VARIANT
        || raw.current_profile_fingerprint.trim().is_empty()
        || raw.current_run_id.trim().is_empty()
        || !valid_contract(contract)
    {
        return Err("asymmetric portfolio observer contract is invalid".into());
    }
    validate_cutoff(raw)?;
    validate_routes(raw)?;
    Ok(())
}

fn valid_contract(contract: &AsymmetricContractRaw) -> bool {
    contract.report_only
        && contract.execution_authority == "none"
        && !contract.runtime_strategy_changed
        && !contract.automatic_strategy_changes
        && !contract.automatic_promotion
        && !contract.performance_gate
        && !contract.balance_gate
        && !contract.trade_count_gate
        && contract.actual_resolved_lifecycles_only
        && !contract.counterfactual_fills_claimed
        && !contract.capital_reallocation_claimed
}

fn validate_cutoff(raw: &AsymmetricForwardRaw) -> Result<(), String> {
    let parsed = DateTime::parse_from_rfc3339(&raw.predeclared_at_utc)
        .map_err(|error| format!("invalid asymmetric observer cutoff: {error}"))?;
    if parsed.timestamp_millis() != raw.entry_cutoff_timestamp_ms {
        return Err("asymmetric observer cutoff identities disagree".into());
    }
    Ok(())
}

fn validate_routes(raw: &AsymmetricForwardRaw) -> Result<(), String> {
    let candidate = route_set(&raw.candidate_route_sides);
    let excluded = route_set(&raw.excluded_symmetric_route_sides);
    let expected_candidate = BTreeSet::from([
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH|long".into(),
        "hype_breakout_onset_bidirectional_v1|HYPE|long".into(),
        "range_onset_bidirectional_v1|SOL|long".into(),
        "range_onset_bidirectional_v1|SOL|short".into(),
    ]);
    let expected_excluded = BTreeSet::from([
        "eth_breakout_precompression_pullback_bidirectional_v1|ETH|short".into(),
        "hype_breakout_onset_bidirectional_v1|HYPE|short".into(),
    ]);
    if candidate != expected_candidate || excluded != expected_excluded {
        return Err("asymmetric portfolio observer route scope is invalid".into());
    }
    Ok(())
}

fn route_set(routes: &[[String; 3]]) -> BTreeSet<String> {
    routes.iter().map(|route| route.join("|")).collect()
}

fn project_economics(
    raw: AsymmetricEconomicsRaw,
    label: &str,
) -> Result<CohortAsymmetricEconomics, String> {
    let optional = [
        raw.profit_factor,
        raw.mean_return_on_margin_pct,
        raw.median_return_on_margin_pct,
        raw.largest_winner_usd,
        raw.net_pnl_excluding_largest_winner_usd,
    ];
    let finite = raw.net_pnl_usd.is_finite()
        && raw.fees_usd.is_finite()
        && raw.funding_usd.is_finite()
        && optional.into_iter().flatten().all(f64::is_finite);
    let counts_match = raw.wins + raw.losses + raw.breakeven == raw.closed_trades;
    let shape_matches = economics_shape_matches(&raw);
    if !finite || !counts_match || !shape_matches || raw.fees_usd < 0.0 {
        return Err(format!(
            "asymmetric portfolio {label} economics are invalid"
        ));
    }
    Ok(CohortAsymmetricEconomics {
        closed_trades: raw.closed_trades,
        wins: raw.wins,
        losses: raw.losses,
        breakeven: raw.breakeven,
        net_pnl_usd: raw.net_pnl_usd,
        fees_usd: raw.fees_usd,
        funding_usd: raw.funding_usd,
        profit_factor: raw.profit_factor,
        median_return_on_margin_pct: raw.median_return_on_margin_pct,
        net_pnl_excluding_largest_winner_usd: raw.net_pnl_excluding_largest_winner_usd,
    })
}

fn economics_shape_matches(raw: &AsymmetricEconomicsRaw) -> bool {
    let has_trades = raw.closed_trades > 0;
    let has_wins = raw.wins > 0;
    let has_losses = raw.losses > 0;
    raw.mean_return_on_margin_pct.is_some() == has_trades
        && raw.median_return_on_margin_pct.is_some() == has_trades
        && raw.largest_winner_usd.is_some() == has_wins
        && raw.net_pnl_excluding_largest_winner_usd.is_some() == has_wins
        && raw.profit_factor.is_some() == has_losses
        && raw.profit_factor.is_none_or(|value| value >= 0.0)
        && raw.largest_winner_usd.is_none_or(|value| value > 0.0)
}

fn validate_evidence_state(state: &str, candidate_trades: usize) -> Result<(), String> {
    let valid = match state {
        "awaiting_post_cutoff_resolution" => candidate_trades == 0,
        "prospective_resolutions_observed" => candidate_trades > 0,
        _ => false,
    };
    if !valid {
        return Err("asymmetric portfolio observer evidence state is invalid".into());
    }
    Ok(())
}
