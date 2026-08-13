//! Strict projection of decision-time L2 context for missed opportunities.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use crate::backend_cohort_eligible_markouts::{
    CohortEligibleBboMarkouts, ObserverExecutableBboMarkoutsRaw, project_eligible_bbo_markouts,
};
use crate::backend_cohort_opportunity_capture::{
    CohortOpportunityCapture, ObserverOpportunityCaptureRaw, project_opportunity_capture,
};

#[path = "backend_cohort_orderbook_opportunity_projection.rs"]
mod projection;

pub(crate) use projection::{
    project_provider_orderbook, validate_eligible_signal_context, validate_pressure_clock,
};

#[derive(Debug, Clone, PartialEq)]
pub struct CohortProviderOrderbookOpportunity {
    pub(crate) by_blocker: BTreeMap<String, CohortOrderbookBlocker>,
    pub(crate) pressure_clock: Option<CohortProviderPressureClock>,
    pub(crate) eligible_signal_context: Option<CohortEligibleSignalContext>,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortProviderPressureClock {
    pub(crate) pressure_unavailable_evaluations: usize,
    pub(crate) causal_book_available: usize,
    pub(crate) book_absent_or_stale: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortEligibleSignalContext {
    pub(crate) eligible_signals: usize,
    pub(crate) pressure_stance: CohortSignalStanceCounts,
    pub(crate) state_5m_stance: CohortSignalStanceCounts,
    pub(crate) context_15m_stance: CohortSignalStanceCounts,
    pub(crate) executable_bbo_markouts: Option<CohortEligibleBboMarkouts>,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortSignalStanceCounts {
    pub(crate) aligned: usize,
    pub(crate) neutral: usize,
    pub(crate) opposed: usize,
    pub(crate) unavailable: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortOrderbookBlocker {
    pub(crate) by_side: BTreeMap<String, CohortOrderbookSide>,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortOrderbookSide {
    pub(crate) horizons: BTreeMap<u16, CohortOrderbookHorizon>,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortOrderbookHorizon {
    pub(crate) independent_resolved: usize,
    pub(crate) aligned: CohortOrderbookGroup,
    pub(crate) opposed: CohortOrderbookGroup,
}

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct CohortOrderbookGroup {
    pub(crate) paths: usize,
    pub(crate) mean_directional_opi: Option<f64>,
    pub(crate) mean_spread_bps: Option<f64>,
    pub(crate) opportunity_capture: CohortOpportunityCapture,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverOrderbookOpportunityRaw {
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderOrderbookRaw>,
    #[serde(default)]
    pub(crate) provider_pressure_clock: Option<ObserverPressureClockRaw>,
    #[serde(default)]
    pub(crate) eligible_signal_context: Option<ObserverEligibleSignalContextRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverEligibleSignalContextRaw {
    contract: ObserverEligibleSignalContractRaw,
    coverage: ObserverEligibleSignalCoverageRaw,
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderSignalContextRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverEligibleSignalContractRaw {
    report_only: bool,
    execution_authority: String,
    signals_are_annotations: bool,
    routing_or_fill_claimed: bool,
    thresholds_selected: bool,
    signal_eligibility_changed: bool,
}

#[derive(Debug, Deserialize)]
struct ObserverEligibleSignalCoverageRaw {
    eligible_signals: usize,
    book_matched: usize,
    book_stale: usize,
    book_missing: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderSignalContextRaw {
    eligible_signals: usize,
    pressure_stance: ObserverSignalStanceCountsRaw,
    state_5m_stance: ObserverSignalStanceCountsRaw,
    context_15m_stance: ObserverSignalStanceCountsRaw,
    #[serde(default)]
    executable_bbo_markouts: Option<ObserverExecutableBboMarkoutsRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverSignalStanceCountsRaw {
    aligned: usize,
    neutral: usize,
    opposed: usize,
    unavailable: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverPressureClockRaw {
    pub(crate) pressure_unavailable_evaluations: usize,
    pub(crate) causal_book_available: usize,
    pub(crate) book_absent_or_stale: usize,
    pub(crate) by_provider_symbol: BTreeMap<String, ObserverProviderPressureClockRaw>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderPressureClockRaw {
    pressure_unavailable_evaluations: usize,
    causal_book_available: usize,
    book_absent_or_stale: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ObserverProviderOrderbookRaw {
    by_blocker: BTreeMap<String, ObserverOrderbookBlockerRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverOrderbookBlockerRaw {
    by_side: BTreeMap<String, ObserverOrderbookSideRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverOrderbookSideRaw {
    horizons: BTreeMap<String, ObserverOrderbookHorizonRaw>,
}

#[derive(Debug, Deserialize)]
struct ObserverOrderbookHorizonRaw {
    independent_resolved: usize,
    aligned: ObserverOrderbookGroupRaw,
    opposed: ObserverOrderbookGroupRaw,
}

#[derive(Debug, Deserialize)]
struct ObserverOrderbookGroupRaw {
    paths: usize,
    mean_directional_opi: Option<f64>,
    mean_spread_bps: Option<f64>,
    opportunity_capture: ObserverOpportunityCaptureRaw,
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::*;

    #[test]
    fn projects_aligned_and_opposed_groups_without_pooling() {
        let raw: ObserverProviderOrderbookRaw = serde_json::from_value(serde_json::json!({
            "by_blocker": {
                "awaiting_breakout": {
                    "by_side": {"long": {"horizons": {"60": {
                        "independent_resolved": 3,
                        "aligned": _group(1, 0.4),
                        "opposed": _group(2, -0.3)
                    }}}}
                }
            }
        }))
        .expect("valid fixture");

        let projected = project_provider_orderbook(Some(&raw), None, None)
            .expect("valid L2 context")
            .expect("L2 context present");
        let horizon = &projected.by_blocker["awaiting_breakout"].by_side["long"].horizons[&60];

        assert_eq!(horizon.independent_resolved, 3);
        assert_eq!(horizon.aligned.paths, 1);
        assert_eq!(horizon.opposed.paths, 2);
    }

    #[test]
    fn projects_eligible_signal_context_as_annotation_only() {
        let raw: ObserverEligibleSignalContextRaw = serde_json::from_value(serde_json::json!({
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "signals_are_annotations": true,
                "routing_or_fill_claimed": false,
                "thresholds_selected": false,
                "signal_eligibility_changed": false
            },
            "coverage": {
                "eligible_signals": 3,
                "book_matched": 3,
                "book_stale": 0,
                "book_missing": 0
            },
            "by_provider_symbol": {
                "provider|BTC": {
                    "eligible_signals": 3,
                    "pressure_stance": {
                        "aligned": 2, "neutral": 0, "opposed": 1, "unavailable": 0
                    },
                    "state_5m_stance": {
                        "aligned": 1, "neutral": 1, "opposed": 0, "unavailable": 1
                    },
                    "context_15m_stance": {
                        "aligned": 0, "neutral": 0, "opposed": 0, "unavailable": 3
                    }
                }
            }
        }))
        .expect("valid fixture");
        let provider_keys = BTreeSet::from(["provider|BTC".to_string()]);

        validate_eligible_signal_context(&raw, &provider_keys).expect("honest contract");
        let projected =
            project_provider_orderbook(None, None, raw.by_provider_symbol.get("provider|BTC"))
                .expect("valid signal context")
                .expect("signal context present");
        let context = projected
            .eligible_signal_context
            .expect("eligible signal context projected");

        assert_eq!(context.eligible_signals, 3);
        assert_eq!(context.pressure_stance.aligned, 2);
        assert_eq!(context.pressure_stance.opposed, 1);
        assert_eq!(context.state_5m_stance.unavailable, 1);
        assert_eq!(context.context_15m_stance.unavailable, 3);
    }

    #[test]
    fn projects_pressure_clock_without_one_blocker_paths() {
        let raw: ObserverProviderPressureClockRaw = serde_json::from_value(serde_json::json!({
            "pressure_unavailable_evaluations": 19,
            "causal_book_available": 19,
            "book_absent_or_stale": 0
        }))
        .expect("valid pressure-clock fixture");

        let projected = project_provider_orderbook(None, Some(&raw), None)
            .expect("valid pressure-clock evidence")
            .expect("pressure-clock evidence present");

        assert!(projected.by_blocker.is_empty());
        assert_eq!(
            projected.pressure_clock,
            Some(CohortProviderPressureClock {
                pressure_unavailable_evaluations: 19,
                causal_book_available: 19,
                book_absent_or_stale: 0,
            })
        );
    }

    #[test]
    fn rejects_pressure_clock_totals_that_disagree_with_provider_rows() {
        let raw: ObserverOrderbookOpportunityRaw = serde_json::from_value(serde_json::json!({
            "by_provider_symbol": {},
            "provider_pressure_clock": {
                "pressure_unavailable_evaluations": 2,
                "causal_book_available": 2,
                "book_absent_or_stale": 0,
                "by_provider_symbol": {
                    "provider|xyz:GOLD": {
                        "pressure_unavailable_evaluations": 1,
                        "causal_book_available": 1,
                        "book_absent_or_stale": 0
                    }
                }
            }
        }))
        .expect("valid wire fixture");
        let keys = BTreeSet::from(["provider|xyz:GOLD".to_string()]);

        assert_eq!(
            validate_pressure_clock(&raw, &keys).unwrap_err(),
            "pressure-clock totals disagree with provider rows"
        );
    }

    #[test]
    fn rejects_pressure_clock_for_unknown_provider_identity() {
        let raw: ObserverOrderbookOpportunityRaw = serde_json::from_value(serde_json::json!({
            "by_provider_symbol": {},
            "provider_pressure_clock": {
                "pressure_unavailable_evaluations": 1,
                "causal_book_available": 1,
                "book_absent_or_stale": 0,
                "by_provider_symbol": {
                    "unknown|xyz:GOLD": {
                        "pressure_unavailable_evaluations": 1,
                        "causal_book_available": 1,
                        "book_absent_or_stale": 0
                    }
                }
            }
        }))
        .expect("valid wire fixture");
        let keys = BTreeSet::from(["provider|xyz:GOLD".to_string()]);

        assert_eq!(
            validate_pressure_clock(&raw, &keys).unwrap_err(),
            "pressure-clock provider is absent from the provider journal"
        );
    }

    fn _group(paths: usize, opi: f64) -> serde_json::Value {
        serde_json::json!({
            "paths": paths,
            "mean_directional_opi": opi,
            "mean_spread_bps": 0.2,
            "opportunity_capture": {
                "resolved": paths,
                "cost_clearing_mfe_count": paths,
                "robust_mfe_count": paths,
                "cost_clearing_close_count": paths,
                "reversed_after_cost_clear_count": 0,
                "mean_close_after_estimated_friction_bps": 5.0,
                "median_close_after_estimated_friction_bps": 4.0,
                "minimum_close_after_estimated_friction_bps": 2.0,
                "maximum_close_after_estimated_friction_bps": 8.0
            }
        })
    }
}
