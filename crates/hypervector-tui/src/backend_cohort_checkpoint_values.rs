//! Validation helpers for typed cohort checkpoint path evidence.

use std::collections::BTreeMap;

use crate::backend_cohort_checkpoint::{
    CohortCheckpointTelemetry, ObserverHorizonEvidence, ObserverSignalOutcomesEvidence,
};
use crate::backend_cohort_opportunity_capture::project_independent_opportunity_capture;
use crate::cohort_observer_evidence::CohortObserverPathEvidence;

#[derive(Debug, serde::Deserialize)]
pub(crate) struct LearningEvidence {
    pub(crate) evidence_state: String,
}

impl CohortCheckpointTelemetry {
    /// Build a configured status when no valid aggregate can be loaded yet.
    pub fn unavailable(issue: impl Into<String>) -> Self {
        Self {
            configured: true,
            issue: Some(issue.into()),
            ..Self::default()
        }
    }
}

pub(crate) fn provider_identity(value: &str) -> Result<(String, String), String> {
    let (strategy, symbol) = value
        .split_once('|')
        .ok_or_else(|| "observer provider key must be strategy|symbol".to_string())?;
    if strategy.is_empty() || symbol.is_empty() || symbol.contains('|') {
        return Err("observer provider key must be strategy|symbol".into());
    }
    Ok((strategy.into(), symbol.into()))
}

pub(crate) fn validated_paths(
    horizons: &BTreeMap<String, ObserverHorizonEvidence>,
) -> Result<BTreeMap<u16, CohortObserverPathEvidence>, String> {
    horizons
        .iter()
        .map(|(horizon, evidence)| {
            let minutes = horizon
                .parse::<u16>()
                .map_err(|_| "observer path horizon must be positive minutes".to_string())?;
            if minutes == 0 {
                return Err("observer path horizon must be positive minutes".into());
            }
            Ok((minutes, validated_path(evidence)?))
        })
        .collect()
}

pub(crate) fn five_minute_path_counts(
    evidence: &ObserverSignalOutcomesEvidence,
) -> Result<(usize, usize), String> {
    let mut resolved = 0usize;
    let mut independent = 0usize;
    for provider in evidence.by_provider_symbol.values() {
        let horizon = provider
            .horizons
            .get("5")
            .ok_or_else(|| "observer signal paths are missing the 5m horizon".to_string())?;
        if horizon.non_overlapping_resolved > horizon.resolved {
            return Err("observer independent path count exceeds resolved paths".into());
        }
        resolved = resolved
            .checked_add(horizon.resolved)
            .ok_or_else(|| "observer resolved path count overflow".to_string())?;
        independent = independent
            .checked_add(horizon.non_overlapping_resolved)
            .ok_or_else(|| "observer independent path count overflow".to_string())?;
    }
    Ok((resolved, independent))
}

pub(crate) fn analysis_mode(mode: &str) -> String {
    if mode == "multi_asset_bidirectional_observer_checkpoint" {
        "forward_observer".into()
    } else {
        "live_execution".into()
    }
}

fn validated_path(value: &ObserverHorizonEvidence) -> Result<CohortObserverPathEvidence, String> {
    if value.non_overlapping_resolved > value.resolved {
        return Err("observer independent path count exceeds resolved paths".into());
    }
    let mean = value.mean_directional_close_return_bps;
    if mean.is_some_and(|number| !number.is_finite()) {
        return Err("observer path mean return must be finite".into());
    }
    let rate = value.positive_directional_rate;
    if rate.is_some_and(|number| !number.is_finite() || !(0.0..=1.0).contains(&number)) {
        return Err("observer path positive rate is outside [0,1]".into());
    }
    let statistics_complete = mean.is_some() && rate.is_some();
    if (value.resolved == 0 && (mean.is_some() || rate.is_some()))
        || (value.resolved > 0 && !statistics_complete)
    {
        return Err("observer path statistics disagree with resolved count".into());
    }
    Ok(CohortObserverPathEvidence {
        resolved: value.resolved,
        independent: value.non_overlapping_resolved,
        censored: value.censored,
        missing_data: value.missing_data,
        mean_directional_return_bps: mean,
        positive_directional_rate: rate,
        opportunity_capture: project_independent_opportunity_capture(
            value.opportunity_capture.as_ref(),
            value.independent_opportunity_capture.as_ref(),
            value.resolved,
            value.non_overlapping_resolved,
        )?,
    })
}
