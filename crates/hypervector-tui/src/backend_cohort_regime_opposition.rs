//! Strict projection of report-only regime-opposition persistence evidence.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort_regime_assessment::{ReflectionContract, validate_contract};

const EXPECTED_PERSISTENCE: [usize; 3] = [1, 3, 5];
const OPPOSITION_THRESHOLD: f64 = -0.5;

/// Sustained contrary regime observations within one trade lifecycle.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortRegimeOppositionEpisode {
    pub completed_decisions: usize,
    pub unavailable_decisions: usize,
    pub coverage_gap_decisions: usize,
    pub opposed_decisions: usize,
    pub first_opposed_decision_ms: Option<u64>,
    pub last_decision_ms: Option<u64>,
    pub latest_structure_support_score: Option<f64>,
    pub maximum_consecutive_opposed: usize,
    pub current_consecutive_opposed: usize,
    pub current_active: bool,
    pub trigger_one_decision_ms: Option<u64>,
    pub trigger_three_decisions_ms: Option<u64>,
    pub trigger_five_decisions_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawRegimeOppositionEpisode {
    schema_version: u16,
    mode: String,
    contract: ReflectionContract,
    opposition_threshold: f64,
    persistence_decisions: Vec<usize>,
    entry_timestamp_ms: u64,
    end_timestamp_ms: u64,
    completed_decisions: usize,
    unavailable_decisions: usize,
    coverage_gap_decisions: usize,
    opposed_decisions: usize,
    first_opposed_decision_ms: Option<u64>,
    last_decision_ms: Option<u64>,
    latest_structure_support_score: Option<f64>,
    maximum_consecutive_opposed: usize,
    current_consecutive_opposed: usize,
    current_active: bool,
    persistence_triggers: BTreeMap<String, Option<u64>>,
}

pub(crate) fn project_regime_opposition(
    raw: Option<RawRegimeOppositionEpisode>,
) -> Result<Option<CohortRegimeOppositionEpisode>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_contract(&value.contract)?;
    validate_identity(&value)?;
    validate_counts(&value)?;
    let triggers = triggers(&value)?;
    validate_timestamps(&value, triggers)?;
    Ok(Some(CohortRegimeOppositionEpisode {
        completed_decisions: value.completed_decisions,
        unavailable_decisions: value.unavailable_decisions,
        coverage_gap_decisions: value.coverage_gap_decisions,
        opposed_decisions: value.opposed_decisions,
        first_opposed_decision_ms: value.first_opposed_decision_ms,
        last_decision_ms: value.last_decision_ms,
        latest_structure_support_score: value.latest_structure_support_score,
        maximum_consecutive_opposed: value.maximum_consecutive_opposed,
        current_consecutive_opposed: value.current_consecutive_opposed,
        current_active: value.current_active,
        trigger_one_decision_ms: triggers[0],
        trigger_three_decisions_ms: triggers[1],
        trigger_five_decisions_ms: triggers[2],
    }))
}

fn validate_identity(value: &RawRegimeOppositionEpisode) -> Result<(), String> {
    if value.schema_version != 1
        || value.mode != "causal_regime_opposition_persistence_v1"
        || (value.opposition_threshold - OPPOSITION_THRESHOLD).abs() > f64::EPSILON
        || value.persistence_decisions != EXPECTED_PERSISTENCE
        || value.entry_timestamp_ms > value.end_timestamp_ms
        || value
            .latest_structure_support_score
            .is_some_and(|score| !score.is_finite() || !(-1.0..=1.0).contains(&score))
    {
        return Err("regime-opposition identity is invalid".into());
    }
    Ok(())
}

fn validate_counts(value: &RawRegimeOppositionEpisode) -> Result<(), String> {
    if value.unavailable_decisions > value.completed_decisions
        || value.opposed_decisions > value.completed_decisions
        || value.maximum_consecutive_opposed > value.opposed_decisions
        || value.current_consecutive_opposed > value.maximum_consecutive_opposed
        || value.current_active != (value.current_consecutive_opposed > 0)
        || value.first_opposed_decision_ms.is_some() != (value.opposed_decisions > 0)
        || value.last_decision_ms.is_some() != (value.completed_decisions > 0)
    {
        return Err("regime-opposition counts are inconsistent".into());
    }
    if value.current_active
        && !value
            .latest_structure_support_score
            .is_some_and(|score| score <= OPPOSITION_THRESHOLD)
    {
        return Err("active regime opposition lacks an opposed latest score".into());
    }
    Ok(())
}

fn triggers(value: &RawRegimeOppositionEpisode) -> Result<[Option<u64>; 3], String> {
    if value.persistence_triggers.len() != 3
        || EXPECTED_PERSISTENCE
            .iter()
            .any(|key| !value.persistence_triggers.contains_key(&key.to_string()))
    {
        return Err("regime-opposition triggers are incomplete".into());
    }
    Ok(EXPECTED_PERSISTENCE.map(|key| value.persistence_triggers[&key.to_string()]))
}

fn validate_timestamps(
    value: &RawRegimeOppositionEpisode,
    triggers: [Option<u64>; 3],
) -> Result<(), String> {
    let timestamps = [
        value.first_opposed_decision_ms,
        value.last_decision_ms,
        triggers[0],
        triggers[1],
        triggers[2],
    ];
    if timestamps
        .into_iter()
        .flatten()
        .any(|timestamp| timestamp < value.entry_timestamp_ms || timestamp > value.end_timestamp_ms)
        || triggers[0] != value.first_opposed_decision_ms
        || triggers[0].is_some() != (value.maximum_consecutive_opposed >= 1)
        || triggers[1].is_some() != (value.maximum_consecutive_opposed >= 3)
        || triggers[2].is_some() != (value.maximum_consecutive_opposed >= 5)
        || !ordered_triggers(triggers)
    {
        return Err("regime-opposition timestamps are inconsistent".into());
    }
    Ok(())
}

fn ordered_triggers(values: [Option<u64>; 3]) -> bool {
    values
        .into_iter()
        .flatten()
        .try_fold(0, |previous, current| {
            (current >= previous).then_some(current)
        })
        .is_some()
}
