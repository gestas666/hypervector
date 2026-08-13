//! Strict closed-lifecycle W/L and net-on-margin performance projection.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort_run_windows::{
    CohortProcessRunWindows, RawProcessRunWindows, project_process_run_windows,
};

#[path = "backend_cohort_trade_performance_projection.rs"]
mod projection;

pub(crate) use projection::{
    project_partition, project_summary, project_trade_performance, validate_aggregate,
};

const RETURN_BASIS: &str = "net_pnl_divided_by_sum_entry_margin";

/// Backend-authored performance summary for one strategy or the portfolio total.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradePerformanceSummary {
    pub closed_trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub breakeven: usize,
    pub win_rate_pct: Option<f64>,
    pub net_pnl_usd: f64,
    pub entry_margin_used_usd: f64,
    pub net_return_on_margin_pct: Option<f64>,
    pub mean_trade_return_on_margin_pct: Option<f64>,
    pub profit_factor: Option<f64>,
    pub fees_usd: f64,
    pub funding_usd: f64,
}

/// Compatible-profile totals and exact per-strategy breakdowns.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradePerformance {
    pub total: CohortTradePerformanceSummary,
    pub by_strategy: BTreeMap<String, CohortTradePerformanceSummary>,
    pub all_time_live: Option<CohortAllTimeTradePerformance>,
    pub profile_fingerprint_count: Option<usize>,
    pub mixed_profile_history: bool,
    pub current_profile: Option<CohortProfileTradePerformance>,
    pub current_run: Option<CohortRunTradePerformance>,
    pub process_run_windows: Option<CohortProcessRunWindows>,
}

/// User-facing armed-live history across policy generations.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortAllTimeTradePerformance {
    pub total: CohortTradePerformanceSummary,
    pub by_strategy: BTreeMap<String, CohortTradePerformanceSummary>,
}

/// Exact current-profile subset retained separately from compatible history.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortProfileTradePerformance {
    pub profile_fingerprint: String,
    pub total: CohortTradePerformanceSummary,
    pub by_strategy: BTreeMap<String, CohortTradePerformanceSummary>,
}

/// Exact current-run subset retained separately from profile and history.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortRunTradePerformance {
    pub run_id: String,
    pub total: CohortTradePerformanceSummary,
    pub by_strategy: BTreeMap<String, CohortTradePerformanceSummary>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawTradePerformance {
    scope: String,
    return_basis: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
    #[serde(default)]
    all_time_live: Option<RawAllTimeTradePerformance>,
    #[serde(default)]
    profile_fingerprint_count: Option<usize>,
    #[serde(default)]
    mixed_profile_history: bool,
    #[serde(default)]
    current_profile: Option<RawProfileTradePerformance>,
    #[serde(default)]
    current_run: Option<RawRunTradePerformance>,
    #[serde(default)]
    process_run_windows: Option<RawProcessRunWindows>,
}

#[derive(Debug, Deserialize)]
struct RawAllTimeTradePerformance {
    scope: String,
    return_basis: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
}

#[derive(Debug, Deserialize)]
struct RawProfileTradePerformance {
    profile_fingerprint: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
}

#[derive(Debug, Deserialize)]
struct RawRunTradePerformance {
    run_id: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct RawTradePerformanceSummary {
    closed_trades: usize,
    wins: usize,
    losses: usize,
    breakeven: usize,
    win_rate_pct: Option<f64>,
    net_pnl_usd: f64,
    entry_margin_used_usd: f64,
    net_return_on_margin_pct: Option<f64>,
    mean_trade_return_on_margin_pct: Option<f64>,
    #[serde(default)]
    profit_factor: Option<f64>,
    fees_usd: f64,
    funding_usd: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projects_current_profile_without_pooling_compatible_history() {
        let raw = serde_json::from_value::<RawTradePerformance>(serde_json::json!({
            "scope":"compatible_profile_history",
            "return_basis":RETURN_BASIS,
            "profile_fingerprint_count":2,
            "mixed_profile_history":true,
            "total":summary(2, 1, 1, 1.0, 10.0, Some(1.0)),
            "by_strategy":{"alpha":summary(2, 1, 1, 1.0, 10.0, Some(1.0))},
            "all_time_live":{
                "scope":"all_live_history",
                "return_basis":RETURN_BASIS,
                "total":summary(3, 2, 1, 2.0, 15.0, Some(2.0)),
                "by_strategy":{"alpha":summary(3, 2, 1, 2.0, 15.0, Some(2.0))}
            },
            "current_profile":{
                "profile_fingerprint":"current-fingerprint",
                "total":summary(1, 0, 1, -0.25, 5.0, Some(0.0)),
                "by_strategy":{"alpha":summary(1, 0, 1, -0.25, 5.0, Some(0.0))}
            },
            "current_run":{
                "run_id":"current-run",
                "total":summary(1, 0, 1, -0.25, 5.0, Some(0.0)),
                "by_strategy":{"alpha":summary(1, 0, 1, -0.25, 5.0, Some(0.0))}
            },
            "process_run_windows":{
                "contract":{
                    "report_only":true,
                    "performance_gate":false,
                    "balance_gate":false,
                    "automatic_strategy_changes":false,
                    "execution_authority":"none"
                },
                "window_basis":"backend_process_run_id",
                "statistical_independence_established":false,
                "run_count":2,
                "runs_with_closes":2,
                "positive_runs":1,
                "negative_runs":1,
                "breakeven_runs":0,
                "positive_run_rate_pct":50.0,
                "net_pnl_usd":1.0,
                "by_run":{
                    "prior-run":{
                        "run_id":"prior-run",
                        "profile_fingerprint":"prior-profile",
                        "total":window_summary(1, 1, 0, 1.25, 5.0, None),
                        "by_strategy":{"alpha":window_summary(1, 1, 0, 1.25, 5.0, None)}
                    },
                    "current-run":{
                        "run_id":"current-run",
                        "profile_fingerprint":"current-fingerprint",
                        "total":window_summary(1, 0, 1, -0.25, 5.0, Some(0.0)),
                        "by_strategy":{"alpha":window_summary(1, 0, 1, -0.25, 5.0, Some(0.0))}
                    }
                },
                "by_provider_symbol":{
                    "alpha|BTC":{
                        "runs_with_closes":2,
                        "positive_runs":1,
                        "negative_runs":1,
                        "breakeven_runs":0,
                        "positive_run_rate_pct":50.0,
                        "net_pnl_usd":1.0,
                        "by_side":{
                            "long":{
                                "runs_with_closes":2,
                                "positive_runs":1,
                                "negative_runs":1,
                                "breakeven_runs":0,
                                "positive_run_rate_pct":50.0,
                                "net_pnl_usd":1.0
                            }
                        }
                    }
                },
                "limitations":[
                    "a backend process restart creates a run window but not statistical independence",
                    "profile changes remain visible and are not pooled as one policy generation",
                    "run-window outcomes are descriptive and have no execution authority"
                ]
            }
        }))
        .expect("current-profile fixture");

        let projected = project_trade_performance(Some(raw), 2)
            .expect("valid performance")
            .expect("performance present");

        assert!(projected.mixed_profile_history);
        let all_time = projected.all_time_live.expect("all-time live history");
        assert_eq!(all_time.total.closed_trades, 3);
        assert_eq!(all_time.total.net_pnl_usd, 2.0);
        assert_eq!(projected.profile_fingerprint_count, Some(2));
        let current = projected.current_profile.expect("current profile");
        assert_eq!(current.profile_fingerprint, "current-fingerprint");
        assert_eq!(current.total.closed_trades, 1);
        assert_eq!(current.total.net_pnl_usd, -0.25);
        let run = projected.current_run.expect("current run");
        assert_eq!(run.run_id, "current-run");
        assert_eq!(run.total.closed_trades, 1);
        assert_eq!(run.total.net_pnl_usd, -0.25);
        let windows = projected.process_run_windows.expect("process windows");
        assert_eq!(windows.run_count, 2);
        assert_eq!(windows.positive_runs, 1);
        assert_eq!(windows.negative_runs, 1);
        assert!(!windows.statistical_independence_established);
        assert_eq!(
            windows.by_run["current-run"].profile_fingerprint,
            "current-fingerprint"
        );
        assert_eq!(windows.by_provider_symbol["alpha|BTC"].positive_runs, 1);
    }

    #[test]
    fn rejects_empty_current_profile_strategy_identity() {
        let raw = serde_json::from_value::<RawTradePerformance>(serde_json::json!({
            "scope":"compatible_profile_history",
            "return_basis":RETURN_BASIS,
            "profile_fingerprint_count":1,
            "mixed_profile_history":false,
            "total":summary(1, 1, 0, 0.25, 5.0, None),
            "by_strategy":{"alpha":summary(1, 1, 0, 0.25, 5.0, None)},
            "current_profile":{
                "profile_fingerprint":"current-fingerprint",
                "total":summary(1, 1, 0, 0.25, 5.0, None),
                "by_strategy":{" ":summary(1, 1, 0, 0.25, 5.0, None)}
            }
        }))
        .expect("invalid current-profile fixture still parses");

        let error = project_trade_performance(Some(raw), 1).expect_err("empty id must fail");

        assert_eq!(error, "current-profile strategy id is empty");
    }

    fn summary(
        closed: usize,
        wins: usize,
        losses: usize,
        net: f64,
        margin: f64,
        profit_factor: Option<f64>,
    ) -> serde_json::Value {
        serde_json::json!({
            "closed_trades":closed,
            "wins":wins,
            "losses":losses,
            "breakeven":0,
            "win_rate_pct":wins as f64 / closed as f64 * 100.0,
            "net_pnl_usd":net,
            "entry_margin_used_usd":margin,
            "net_return_on_margin_pct":net / margin * 100.0,
            "mean_trade_return_on_margin_pct":net / margin * 100.0,
            "profit_factor":profit_factor,
            "fees_usd":0.02,
            "funding_usd":0.001
        })
    }

    fn window_summary(
        closed: usize,
        wins: usize,
        losses: usize,
        net: f64,
        margin: f64,
        profit_factor: Option<f64>,
    ) -> serde_json::Value {
        let mut value = summary(closed, wins, losses, net, margin, profit_factor);
        value["fees_usd"] = serde_json::json!(0.01);
        value["funding_usd"] = serde_json::json!(0.0005);
        value
    }
}
