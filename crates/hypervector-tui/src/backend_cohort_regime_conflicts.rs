//! Strict projection of report-only regime routing counterfactual evidence.

use std::collections::BTreeMap;

use serde::Deserialize;

/// Compact regime-versus-static routing evidence for TUI views.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortRegimeConflictEvidence {
    pub state: String,
    pub conflicts: usize,
    pub changed_static_choice: usize,
    pub directionally_comparable: usize,
    pub same_direction_provider_only: usize,
    pub five_minute: Option<CohortRegimeConflictHorizon>,
    pub evidence_state: String,
}

/// One causal forward horizon comparing the two routing choices.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortRegimeConflictHorizon {
    pub resolved: usize,
    pub independent: usize,
    pub censored: usize,
    pub missing_data: usize,
    pub regime_wins: usize,
    pub static_wins: usize,
    pub ties: usize,
    pub mean_advantage_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RegimeConflictEvidenceRaw {
    schema_version: u64,
    mode: String,
    state: String,
    contract: RegimeConflictContract,
    conflicts: usize,
    conflicts_changing_static_choice: usize,
    directionally_comparable_conflicts: usize,
    same_direction_provider_only: usize,
    horizons: BTreeMap<String, RegimeConflictHorizonRaw>,
    evidence_state: String,
}

#[derive(Debug, Deserialize)]
struct RegimeConflictContract {
    report_only: bool,
    counterfactual_only: bool,
    fills_assumed: bool,
    pnl_claimed: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
}

#[derive(Debug, Deserialize)]
struct RegimeConflictHorizonRaw {
    resolved: usize,
    non_overlapping_resolved: usize,
    censored: usize,
    missing_data: usize,
    regime_preference_wins: usize,
    static_priority_wins: usize,
    ties: usize,
    mean_regime_advantage_bps: Option<f64>,
}

pub(crate) fn project_regime_conflicts(
    raw: Option<RegimeConflictEvidenceRaw>,
) -> Result<Option<CohortRegimeConflictEvidence>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_envelope(&value)?;
    let five_minute = value.horizons.get("5").map(project_horizon).transpose()?;
    if value.state == "active" && five_minute.is_none() {
        return Err("active regime conflict journal is missing 5m evidence".into());
    }
    Ok(Some(CohortRegimeConflictEvidence {
        state: value.state,
        conflicts: value.conflicts,
        changed_static_choice: value.conflicts_changing_static_choice,
        directionally_comparable: value.directionally_comparable_conflicts,
        same_direction_provider_only: value.same_direction_provider_only,
        five_minute,
        evidence_state: value.evidence_state,
    }))
}

fn validate_envelope(value: &RegimeConflictEvidenceRaw) -> Result<(), String> {
    if value.schema_version != 1
        || value.mode != "regime_conflict_counterfactual_journal"
        || !matches!(value.state.as_str(), "active" | "not_active")
        || value.evidence_state.trim().is_empty()
    {
        return Err("regime conflict journal envelope is invalid".into());
    }
    validate_contract(&value.contract)?;
    if value.conflicts_changing_static_choice > value.conflicts
        || value.directionally_comparable_conflicts > value.conflicts_changing_static_choice
        || value.same_direction_provider_only > value.conflicts_changing_static_choice
        || value.directionally_comparable_conflicts + value.same_direction_provider_only
            > value.conflicts_changing_static_choice
    {
        return Err("regime conflict journal counts are inconsistent".into());
    }
    if value.state == "not_active" && value.conflicts != 0 {
        return Err("inactive regime conflict journal cannot report conflicts".into());
    }
    Ok(())
}

fn validate_contract(value: &RegimeConflictContract) -> Result<(), String> {
    if !value.report_only
        || !value.counterfactual_only
        || value.fills_assumed
        || value.pnl_claimed
        || value.execution_authority != "none"
        || value.runtime_strategy_changed
        || value.automatic_strategy_changes
    {
        return Err("regime conflict journal exceeded report-only authority".into());
    }
    Ok(())
}

fn project_horizon(
    value: &RegimeConflictHorizonRaw,
) -> Result<CohortRegimeConflictHorizon, String> {
    if value.non_overlapping_resolved > value.resolved
        || value.regime_preference_wins + value.static_priority_wins + value.ties != value.resolved
        || value
            .mean_regime_advantage_bps
            .is_some_and(|number| !number.is_finite())
        || (value.resolved == 0 && value.mean_regime_advantage_bps.is_some())
        || (value.resolved > 0 && value.mean_regime_advantage_bps.is_none())
    {
        return Err("regime conflict horizon evidence is inconsistent".into());
    }
    Ok(CohortRegimeConflictHorizon {
        resolved: value.resolved,
        independent: value.non_overlapping_resolved,
        censored: value.censored,
        missing_data: value.missing_data,
        regime_wins: value.regime_preference_wins,
        static_wins: value.static_priority_wins,
        ties: value.ties,
        mean_advantage_bps: value.mean_regime_advantage_bps,
    })
}
