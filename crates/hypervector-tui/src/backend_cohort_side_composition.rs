//! Strict projection of report-only provider-symbol-side research rankings.

use serde::Deserialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

const MODE: &str = "cohort_separate_side_composition";
const HISTORY_SCOPE: &str = "all_live_history_mixed_profiles";

/// One ranked provider-symbol-side research component.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortSideComponent {
    pub component: String,
    pub priority: usize,
    pub evidence_tier: String,
    pub evidence_tension: bool,
    pub trades: usize,
    pub net_pnl_usd: f64,
    pub usd_profit_factor: Option<f64>,
    pub normalized_profit_factor: Option<f64>,
}

/// Backend-authored route-side frontier for research display only.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortSideComposition {
    pub source_run_id: String,
    pub as_of_utc: String,
    pub components: usize,
    pub long_frontier: Vec<CohortSideComponent>,
    pub short_frontier: Vec<CohortSideComponent>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct SideCompositionRaw {
    schema_version: u64,
    mode: String,
    contract: SideCompositionContractRaw,
    source: SideCompositionSourceRaw,
    summary: SideCompositionSummaryRaw,
    frontier: SideFrontierRaw,
    components: BTreeMap<String, Value>,
}

#[derive(Debug, Deserialize)]
struct SideCompositionContractRaw {
    report_only: bool,
    execution_authority: String,
    performance_gate: bool,
    balance_gate: bool,
    trade_count_gate: bool,
    automatic_promotion: bool,
    runtime_strategy_changed: bool,
    ranking_only: bool,
}

#[derive(Debug, Deserialize)]
struct SideCompositionSourceRaw {
    run_id: String,
    profile_id: String,
    profile_fingerprint: String,
    as_of_utc: String,
    live_history_scope: String,
}

#[derive(Debug, Deserialize)]
struct SideCompositionSummaryRaw {
    components: usize,
    long_frontier_components: usize,
    short_frontier_components: usize,
    both_side_frontier_available: bool,
    evidence_tiers: BTreeMap<String, usize>,
    automatic_promotion: bool,
    runtime_strategy_changed: bool,
}

#[derive(Debug, Deserialize)]
struct SideFrontierRaw {
    long: Vec<CohortSideComponentRaw>,
    short: Vec<CohortSideComponentRaw>,
}

#[derive(Debug, Deserialize)]
struct CohortSideComponentRaw {
    component: String,
    priority: usize,
    evidence_tier: String,
    evidence_tension: bool,
    trades: usize,
    net_pnl_usd: f64,
    usd_profit_factor: Option<f64>,
    normalized_profit_factor: Option<f64>,
}

pub(crate) fn project_side_composition(
    raw: Option<SideCompositionRaw>,
    expected_run_id: Option<&str>,
    expected_profile_id: Option<&str>,
    expected_profile_fingerprint: Option<&str>,
) -> Result<Option<CohortSideComposition>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_contract(&raw)?;
    validate_source(
        &raw.source,
        expected_run_id,
        expected_profile_id,
        expected_profile_fingerprint,
    )?;
    validate_summary(&raw)?;
    let long = project_frontier(raw.frontier.long, "long", &raw.components)?;
    let short = project_frontier(raw.frontier.short, "short", &raw.components)?;
    Ok(Some(CohortSideComposition {
        source_run_id: raw.source.run_id,
        as_of_utc: raw.source.as_of_utc,
        components: raw.summary.components,
        long_frontier: long,
        short_frontier: short,
    }))
}

fn validate_contract(raw: &SideCompositionRaw) -> Result<(), String> {
    let contract = &raw.contract;
    if raw.schema_version != 2
        || raw.mode != MODE
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.performance_gate
        || contract.balance_gate
        || contract.trade_count_gate
        || contract.automatic_promotion
        || contract.runtime_strategy_changed
        || !contract.ranking_only
    {
        return Err("side composition contract is invalid".into());
    }
    Ok(())
}

fn validate_source(
    source: &SideCompositionSourceRaw,
    expected_run_id: Option<&str>,
    expected_profile_id: Option<&str>,
    expected_profile_fingerprint: Option<&str>,
) -> Result<(), String> {
    if source.run_id.is_empty()
        || source.profile_id.is_empty()
        || source.profile_fingerprint.is_empty()
        || source.as_of_utc.is_empty()
        || source.live_history_scope != HISTORY_SCOPE
    {
        return Err("side composition source identity is invalid".into());
    }
    validate_identity("run", &source.run_id, expected_run_id)?;
    validate_identity("profile", &source.profile_id, expected_profile_id)?;
    validate_identity(
        "profile fingerprint",
        &source.profile_fingerprint,
        expected_profile_fingerprint,
    )
}

fn validate_identity(label: &str, actual: &str, expected: Option<&str>) -> Result<(), String> {
    if expected.is_some_and(|value| value != actual) {
        return Err(format!("side composition {label} identity mismatch"));
    }
    Ok(())
}

fn validate_summary(raw: &SideCompositionRaw) -> Result<(), String> {
    let summary = &raw.summary;
    let tier_total: usize = summary.evidence_tiers.values().sum();
    let both_sides = !raw.frontier.long.is_empty() && !raw.frontier.short.is_empty();
    if summary.components != raw.components.len()
        || summary.components != tier_total
        || summary.long_frontier_components != raw.frontier.long.len()
        || summary.short_frontier_components != raw.frontier.short.len()
        || summary.both_side_frontier_available != both_sides
        || summary.automatic_promotion
        || summary.runtime_strategy_changed
    {
        return Err("side composition summary does not reconcile".into());
    }
    Ok(())
}

fn project_frontier(
    rows: Vec<CohortSideComponentRaw>,
    side: &str,
    components: &BTreeMap<String, Value>,
) -> Result<Vec<CohortSideComponent>, String> {
    let mut identities = BTreeSet::new();
    rows.into_iter()
        .map(|row| {
            validate_component(&row, side, components, &mut identities)?;
            Ok(CohortSideComponent {
                component: row.component,
                priority: row.priority,
                evidence_tier: row.evidence_tier,
                evidence_tension: row.evidence_tension,
                trades: row.trades,
                net_pnl_usd: row.net_pnl_usd,
                usd_profit_factor: row.usd_profit_factor,
                normalized_profit_factor: row.normalized_profit_factor,
            })
        })
        .collect()
}

fn validate_component(
    row: &CohortSideComponentRaw,
    side: &str,
    components: &BTreeMap<String, Value>,
    identities: &mut BTreeSet<String>,
) -> Result<(), String> {
    let tier_valid = matches!(
        row.evidence_tier.as_str(),
        "historical_supportive_no_live"
            | "positive_sparse_mixed_profile"
            | "repeated_positive_mixed_profile"
    );
    let values_valid = row.net_pnl_usd.is_finite()
        && row
            .usd_profit_factor
            .is_none_or(|value| value.is_finite() && value >= 0.0)
        && row
            .normalized_profit_factor
            .is_none_or(|value| value.is_finite() && value >= 0.0);
    if !row.component.ends_with(&format!("|{side}"))
        || !components.contains_key(&row.component)
        || !identities.insert(row.component.clone())
        || row.priority < 2
        || !tier_valid
        || !values_valid
    {
        return Err("side composition frontier component is invalid".into());
    }
    Ok(())
}
