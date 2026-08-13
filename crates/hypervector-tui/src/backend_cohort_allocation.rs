//! Strict projection of a report-only provider allocation challenger.

#[path = "backend_cohort_allocation_projection.rs"]
mod projection;

pub(crate) use projection::{AllocationChallengerRaw, project_allocation_challenger};

/// One current or candidate sizing projection.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationProjection {
    pub configured_leverage: f64,
    pub configured_margin_fraction: f64,
    pub configured_max_notional_usd: f64,
    pub uncapped_notional_usd: f64,
    pub planned_notional_usd: f64,
    pub planned_margin_usd: f64,
    pub effective_margin_fraction: f64,
    pub cap_binding: bool,
}

/// Portfolio-level current/candidate exposure comparison.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationPortfolio {
    pub current_maximum_margin_fraction: f64,
    pub candidate_maximum_margin_fraction: f64,
    pub change_percentage_points: f64,
}

/// Exact resolved live sample attached to the candidate.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationExecutionSample {
    pub status: String,
    pub closed_trades: Option<usize>,
    pub net_pnl_usd: Option<f64>,
    pub profit_factor: Option<f64>,
}

/// One directional visible-depth capacity summary.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationCapacitySide {
    pub complete_rate: f64,
    pub bbo_fill_rate: f64,
    pub median_impact_bps: Option<f64>,
    pub p95_impact_bps: Option<f64>,
    pub maximum_impact_bps: Option<f64>,
    pub minimum_bbo_notional_usd: f64,
}

/// Recent report-only public-L2 evidence for the candidate notional.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationCapacity {
    pub snapshot_count: usize,
    pub candidate_notional_usd: f64,
    pub long: CohortAllocationCapacitySide,
    pub short: CohortAllocationCapacitySide,
}

/// Execution-incapable candidate comparison displayed by the TUI.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAllocationChallenger {
    pub status: String,
    pub target_provider_symbol: String,
    pub account_value_usd: f64,
    pub current: CohortAllocationProjection,
    pub candidate: CohortAllocationProjection,
    pub effective_change: bool,
    pub portfolio: CohortAllocationPortfolio,
    pub execution_sample: CohortAllocationExecutionSample,
    pub visible_depth_capacity: Option<CohortAllocationCapacity>,
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{AllocationChallengerRaw, project_allocation_challenger};
    use crate::backend_cohort_risk_utilization::{
        RiskUtilizationEvidenceRaw, project_risk_utilization,
    };

    #[test]
    fn projects_an_ungated_report_only_candidate() {
        let risk = risk();
        let raw: AllocationChallengerRaw =
            serde_json::from_value(candidate()).expect("candidate shape");

        let projected = project_allocation_challenger(Some(raw), Some(&risk))
            .expect("valid challenger")
            .expect("configured challenger");

        assert_eq!(projected.status, "candidate_not_active");
        assert_eq!(projected.current.planned_notional_usd, 25.0);
        assert_eq!(projected.candidate.planned_notional_usd, 75.0);
        assert_eq!(projected.portfolio.candidate_maximum_margin_fraction, 0.03);
        assert_eq!(projected.execution_sample.closed_trades, Some(4));
        assert_eq!(
            projected
                .visible_depth_capacity
                .expect("capacity")
                .snapshot_count,
            240
        );
    }

    #[test]
    fn rejects_a_candidate_that_claims_a_balance_gate() {
        let risk = risk();
        let mut value = candidate();
        value["contract"]["balance_gate"] = true.into();
        let raw = serde_json::from_value(value).expect("candidate shape");

        let error = project_allocation_challenger(Some(raw), Some(&risk))
            .expect_err("balance gate must fail");

        assert!(error.contains("contract is invalid"));
    }

    fn risk() -> crate::backend_cohort_risk_utilization::CohortRiskUtilization {
        let raw: RiskUtilizationEvidenceRaw = serde_json::from_value(json!({
            "schema_version": 1,
            "mode": "cohort_runtime_risk_utilization_v1",
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "performance_gate": false,
                "balance_gate": false,
                "automatic_sizing_change": false
            },
            "account_value_usd": 500.0,
            "summary": {
                "configured_assets": 1,
                "cap_bound_assets": 1,
                "configured_maximum_positions": 1,
                "provider_symbols": 1,
                "provider_symbol_overrides": 0,
                "maximum_simultaneous_effective_margin_fraction": 0.01
            },
            "by_asset": {"HYPE": projection(25.0)},
            "by_provider_symbol": {
                "hype_breakout_onset_bidirectional_v1|HYPE": {
                    "sizing_source": "asset_default",
                    "configured_leverage": 5.0,
                    "configured_margin_fraction": 0.03,
                    "configured_max_notional_usd": 25.0,
                    "uncapped_notional_usd": 75.0,
                    "planned_notional_usd": 25.0,
                    "planned_margin_usd": 5.0,
                    "effective_margin_fraction": 0.01,
                    "notional_fraction_of_equity": 0.05,
                    "cap_utilization_ratio": 1.0 / 3.0,
                    "cap_binding": true
                }
            }
        }))
        .expect("risk shape");
        project_risk_utilization(Some(raw))
            .expect("valid risk")
            .expect("configured risk")
    }

    fn projection(cap: f64) -> Value {
        json!({
            "configured_leverage": 5.0,
            "configured_margin_fraction": 0.03,
            "configured_max_notional_usd": cap,
            "uncapped_notional_usd": 75.0,
            "planned_notional_usd": cap,
            "planned_margin_usd": cap / 5.0,
            "effective_margin_fraction": cap / 5.0 / 500.0,
            "notional_fraction_of_equity": cap / 500.0,
            "cap_utilization_ratio": cap / 75.0,
            "cap_binding": 75.0 > cap
        })
    }

    fn candidate() -> Value {
        let mut proposed = projection(75.0);
        proposed["effective_change"] = true.into();
        json!({
            "schema_version": 1,
            "mode": "cohort_selective_allocation_challenger_v1",
            "status": "candidate_not_active",
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_sizing_change": false,
                "automatic_promotion": false,
                "performance_gate": false,
                "balance_gate": false
            },
            "target_provider_symbol": "hype_breakout_onset_bidirectional_v1|HYPE",
            "account_value_usd": 500.0,
            "current": projection(25.0),
            "candidate": proposed,
            "portfolio": {
                "current_maximum_margin_fraction": 0.01,
                "candidate_maximum_margin_fraction": 0.03,
                "change_percentage_points": 2.0
            },
            "required_profile_changes": {
                "asset": "HYPE",
                "candidate_asset_ceiling_usd": 75.0,
                "candidate_target_cap_usd": 75.0,
                "pinned_provider_symbols": [
                    "hulk_expansion_bidirectional_tuned_v2|HYPE",
                    "range_onset_bidirectional_v1|HYPE"
                ],
                "restart_required": true
            },
            "execution_sample": {
                "status": "resolved_live_sample",
                "closed_trades": 4,
                "net_pnl_usd": 1.004659,
                "profit_factor": 5.486747
            },
            "visible_depth_capacity": {
                "status": "observed",
                "symbol": "HYPE",
                "snapshot_count": 240,
                "current_notional_usd": 25.0,
                "candidate_notional_usd": 75.0,
                "window_start_timestamp_ms": 1,
                "window_end_timestamp_ms": 240,
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "fills_assumed": false,
                    "promotion_gate": false
                },
                "by_side": {
                    "long": capacity_side(),
                    "short": capacity_side()
                },
                "limitations": ["public depth can cancel"]
            },
            "profit_forecast": null,
            "limitations": ["descriptive sample only"]
        })
    }

    fn capacity_side() -> Value {
        json!({
            "complete_rate": 1.0,
            "bbo_fill_rate": 0.99,
            "median_impact_bps": 0.0,
            "p95_impact_bps": 0.02,
            "maximum_impact_bps": 0.08,
            "minimum_bbo_notional_usd": 500.0
        })
    }
}
