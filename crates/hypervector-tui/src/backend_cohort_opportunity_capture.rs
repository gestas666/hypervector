//! Strict projection of report-only causal opportunity-capture evidence.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort_checkpoint::ObserverHorizonEvidence;
use crate::backend_cohort_checkpoint_values::validated_paths;
use crate::cohort_observer_evidence::CohortObserverPathEvidence;

#[derive(Debug, Clone, PartialEq)]
pub struct CohortOpportunityCapture {
    pub resolved: usize,
    pub cost_clearing_mfe_count: usize,
    pub robust_mfe_count: usize,
    pub cost_clearing_close_count: usize,
    pub reversed_after_cost_clear_count: usize,
    pub mean_close_after_estimated_friction_bps: Option<f64>,
    pub median_close_after_estimated_friction_bps: Option<f64>,
    pub minimum_close_after_estimated_friction_bps: Option<f64>,
    pub maximum_close_after_estimated_friction_bps: Option<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortOneBlockerNearMisses {
    pub evaluations: usize,
    pub by_blocker: BTreeMap<String, CohortOneBlockerGroup>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortOneBlockerGroup {
    pub evaluations: usize,
    pub paths: BTreeMap<u16, CohortObserverPathEvidence>,
    pub by_side: BTreeMap<String, CohortOneBlockerSide>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CohortOneBlockerSide {
    pub evaluations: usize,
    pub paths: BTreeMap<u16, CohortObserverPathEvidence>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverOpportunityCaptureRaw {
    resolved: usize,
    cost_clearing_mfe_count: usize,
    robust_mfe_count: usize,
    cost_clearing_close_count: usize,
    reversed_after_cost_clear_count: usize,
    mean_close_after_estimated_friction_bps: Option<f64>,
    median_close_after_estimated_friction_bps: Option<f64>,
    minimum_close_after_estimated_friction_bps: Option<f64>,
    maximum_close_after_estimated_friction_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverOneBlockerNearMissesRaw {
    pub(crate) evaluations: usize,
    pub(crate) by_blocker: BTreeMap<String, ObserverOneBlockerGroupRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverOneBlockerGroupRaw {
    pub(crate) evaluations: usize,
    pub(crate) horizons: BTreeMap<String, ObserverHorizonEvidence>,
    #[serde(default)]
    pub(crate) by_side: BTreeMap<String, ObserverOneBlockerSideRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverOneBlockerSideRaw {
    pub(crate) evaluations: usize,
    pub(crate) horizons: BTreeMap<String, ObserverHorizonEvidence>,
}

pub(crate) fn project_opportunity_capture(
    raw: Option<&ObserverOpportunityCaptureRaw>,
    resolved: usize,
) -> Result<Option<CohortOpportunityCapture>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let counts = [
        value.cost_clearing_mfe_count,
        value.robust_mfe_count,
        value.cost_clearing_close_count,
    ];
    if value.resolved != resolved
        || counts.into_iter().any(|count| count > resolved)
        || value.robust_mfe_count > value.cost_clearing_mfe_count
        || value.reversed_after_cost_clear_count > value.cost_clearing_mfe_count
    {
        return Err("opportunity-capture counts disagree with resolved paths".into());
    }
    validate_distribution(value, resolved)?;
    Ok(Some(CohortOpportunityCapture {
        resolved,
        cost_clearing_mfe_count: value.cost_clearing_mfe_count,
        robust_mfe_count: value.robust_mfe_count,
        cost_clearing_close_count: value.cost_clearing_close_count,
        reversed_after_cost_clear_count: value.reversed_after_cost_clear_count,
        mean_close_after_estimated_friction_bps: value.mean_close_after_estimated_friction_bps,
        median_close_after_estimated_friction_bps: value.median_close_after_estimated_friction_bps,
        minimum_close_after_estimated_friction_bps: value
            .minimum_close_after_estimated_friction_bps,
        maximum_close_after_estimated_friction_bps: value
            .maximum_close_after_estimated_friction_bps,
    }))
}

fn validate_distribution(
    value: &ObserverOpportunityCaptureRaw,
    resolved: usize,
) -> Result<(), String> {
    let distribution = [
        value.median_close_after_estimated_friction_bps,
        value.minimum_close_after_estimated_friction_bps,
        value.maximum_close_after_estimated_friction_bps,
    ];
    if value
        .mean_close_after_estimated_friction_bps
        .is_some_and(|number| !number.is_finite())
        || distribution
            .iter()
            .flatten()
            .any(|number| !number.is_finite())
    {
        return Err("opportunity-capture distribution must be finite".into());
    }
    let present = distribution
        .iter()
        .filter(|number| number.is_some())
        .count();
    if present != 0 && present != distribution.len() {
        return Err("opportunity-capture distribution must be complete".into());
    }
    if resolved == 0 && present != 0 {
        return Err("empty opportunity capture cannot carry a distribution".into());
    }
    if let [Some(median), Some(minimum), Some(maximum)] = distribution
        && (minimum > median || median > maximum)
    {
        return Err("opportunity-capture distribution order is invalid".into());
    }
    Ok(())
}

pub(crate) fn project_independent_opportunity_capture(
    raw: Option<&ObserverOpportunityCaptureRaw>,
    independent: Option<&ObserverOpportunityCaptureRaw>,
    resolved: usize,
    independent_resolved: usize,
) -> Result<Option<CohortOpportunityCapture>, String> {
    if let Some(value) = independent {
        return project_opportunity_capture(Some(value), independent_resolved);
    }
    if resolved == independent_resolved {
        return project_opportunity_capture(raw, resolved);
    }
    Ok(None)
}

pub(crate) fn project_one_blocker_near_misses(
    raw: Option<&ObserverOneBlockerNearMissesRaw>,
) -> Result<Option<CohortOneBlockerNearMisses>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let mut total = 0usize;
    let mut by_blocker = BTreeMap::new();
    for (blocker, group) in &value.by_blocker {
        if blocker.trim().is_empty() || group.evaluations == 0 {
            return Err("one-blocker near-miss labels and counts must be positive".into());
        }
        total = total
            .checked_add(group.evaluations)
            .ok_or("one-blocker near-miss count overflow")?;
        let by_side = project_one_blocker_sides(group)?;
        by_blocker.insert(
            blocker.clone(),
            CohortOneBlockerGroup {
                evaluations: group.evaluations,
                paths: validated_paths(&group.horizons)?,
                by_side,
            },
        );
    }
    if total != value.evaluations {
        return Err("one-blocker near-miss groups disagree with total".into());
    }
    Ok(Some(CohortOneBlockerNearMisses {
        evaluations: value.evaluations,
        by_blocker,
    }))
}

fn project_one_blocker_sides(
    group: &ObserverOneBlockerGroupRaw,
) -> Result<BTreeMap<String, CohortOneBlockerSide>, String> {
    let mut total = 0usize;
    let mut output = BTreeMap::new();
    for (side, evidence) in &group.by_side {
        if !matches!(side.as_str(), "long" | "short") || evidence.evaluations == 0 {
            return Err(
                "one-blocker side evidence must be long or short with positive count".into(),
            );
        }
        total = total
            .checked_add(evidence.evaluations)
            .ok_or("one-blocker side count overflow")?;
        output.insert(
            side.clone(),
            CohortOneBlockerSide {
                evaluations: evidence.evaluations,
                paths: validated_paths(&evidence.horizons)?,
            },
        );
    }
    if !output.is_empty() && total != group.evaluations {
        return Err("one-blocker side groups disagree with blocker total".into());
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_capture_count_larger_than_resolved_paths() {
        let raw = ObserverOpportunityCaptureRaw {
            resolved: 1,
            cost_clearing_mfe_count: 2,
            robust_mfe_count: 1,
            cost_clearing_close_count: 1,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(3.0),
            median_close_after_estimated_friction_bps: Some(3.0),
            minimum_close_after_estimated_friction_bps: Some(3.0),
            maximum_close_after_estimated_friction_bps: Some(3.0),
        };

        assert!(project_opportunity_capture(Some(&raw), 1).is_err());
    }

    #[test]
    fn prefers_independent_capture_when_raw_paths_overlap() {
        let raw = ObserverOpportunityCaptureRaw {
            resolved: 3,
            cost_clearing_mfe_count: 2,
            robust_mfe_count: 2,
            cost_clearing_close_count: 2,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(5.0),
            median_close_after_estimated_friction_bps: Some(5.0),
            minimum_close_after_estimated_friction_bps: Some(5.0),
            maximum_close_after_estimated_friction_bps: Some(5.0),
        };
        let independent = ObserverOpportunityCaptureRaw {
            resolved: 2,
            cost_clearing_mfe_count: 1,
            robust_mfe_count: 1,
            cost_clearing_close_count: 1,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(-2.0),
            median_close_after_estimated_friction_bps: Some(-2.5),
            minimum_close_after_estimated_friction_bps: Some(-4.0),
            maximum_close_after_estimated_friction_bps: Some(-1.0),
        };

        let projected =
            project_independent_opportunity_capture(Some(&raw), Some(&independent), 3, 2)
                .expect("valid independent capture")
                .expect("capture present");

        assert_eq!(projected.resolved, 2);
        assert_eq!(projected.robust_mfe_count, 1);
        assert_eq!(
            projected.mean_close_after_estimated_friction_bps,
            Some(-2.0)
        );
        assert_eq!(
            projected.median_close_after_estimated_friction_bps,
            Some(-2.5)
        );
    }

    #[test]
    fn rejects_partial_or_misordered_capture_distribution() {
        let partial = ObserverOpportunityCaptureRaw {
            resolved: 2,
            cost_clearing_mfe_count: 1,
            robust_mfe_count: 1,
            cost_clearing_close_count: 1,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(1.0),
            median_close_after_estimated_friction_bps: Some(0.0),
            minimum_close_after_estimated_friction_bps: None,
            maximum_close_after_estimated_friction_bps: Some(2.0),
        };
        assert!(project_opportunity_capture(Some(&partial), 2).is_err());

        let misordered = ObserverOpportunityCaptureRaw {
            resolved: 2,
            cost_clearing_mfe_count: 1,
            robust_mfe_count: 1,
            cost_clearing_close_count: 1,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(1.0),
            median_close_after_estimated_friction_bps: Some(0.0),
            minimum_close_after_estimated_friction_bps: Some(3.0),
            maximum_close_after_estimated_friction_bps: Some(2.0),
        };

        assert!(project_opportunity_capture(Some(&misordered), 2).is_err());
    }

    #[test]
    fn accepts_legacy_capture_without_distribution() {
        let legacy = ObserverOpportunityCaptureRaw {
            resolved: 1,
            cost_clearing_mfe_count: 1,
            robust_mfe_count: 0,
            cost_clearing_close_count: 1,
            reversed_after_cost_clear_count: 0,
            mean_close_after_estimated_friction_bps: Some(1.0),
            median_close_after_estimated_friction_bps: None,
            minimum_close_after_estimated_friction_bps: None,
            maximum_close_after_estimated_friction_bps: None,
        };

        assert!(project_opportunity_capture(Some(&legacy), 1).is_ok());
    }

    #[test]
    fn projects_one_blocker_sides_without_pooling_them() {
        let horizon = ObserverHorizonEvidence {
            resolved: 1,
            non_overlapping_resolved: 1,
            censored: 0,
            missing_data: 0,
            mean_directional_close_return_bps: Some(20.0),
            positive_directional_rate: Some(1.0),
            opportunity_capture: None,
            independent_opportunity_capture: None,
        };
        let raw = ObserverOneBlockerNearMissesRaw {
            evaluations: 1,
            by_blocker: BTreeMap::from([(
                "awaiting_breakout".into(),
                ObserverOneBlockerGroupRaw {
                    evaluations: 1,
                    horizons: BTreeMap::from([("60".into(), horizon)]),
                    by_side: BTreeMap::from([(
                        "long".into(),
                        ObserverOneBlockerSideRaw {
                            evaluations: 1,
                            horizons: BTreeMap::new(),
                        },
                    )]),
                },
            )]),
        };

        let projected = project_one_blocker_near_misses(Some(&raw))
            .expect("valid side evidence")
            .expect("near misses present");

        assert_eq!(
            projected.by_blocker["awaiting_breakout"].by_side["long"].evaluations,
            1
        );
    }
}
