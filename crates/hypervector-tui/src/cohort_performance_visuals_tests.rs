use super::*;
use crate::backend_cohort_trade_performance::{
    CohortProfileTradePerformance, CohortRunTradePerformance, CohortTradePerformance,
    CohortTradePerformanceSummary,
};
use serde_json::json;

fn trade(side: &str, pnl: f64) -> CohortTradeReflection {
    CohortTradeReflection {
        side: side.into(),
        net_pnl_usd: pnl,
        ..CohortTradeReflection::default()
    }
}

fn fill(slippage: Option<f64>, ack: Option<u64>, markout: Option<f64>) -> CohortFill {
    serde_json::from_value(json!({
        "symbol":"BTC", "strategy_id":"test", "operation":"open",
        "trade_id":1, "oid":2, "venue_timestamp_ms":3,
        "price":100.0, "size":0.1, "side":"B", "direction":"Open Long",
        "fee_usd":0.01, "closed_pnl_usd":0.0, "expected_price":100.0,
        "slippage_bps":slippage, "acknowledgement_latency_ms":ack,
        "markout_bps":markout, "markout_horizon_ms":5000,
        "exit_reason":null
    }))
    .expect("valid fill")
}

#[test]
fn directional_summary_retains_wins_losses_and_net_pnl() {
    let trades = [
        trade("long", 0.90),
        trade("long", -0.20),
        trade("short", 0.30),
    ];

    assert_eq!(
        summarize_direction(trades.iter(), "long"),
        OutcomeSummary {
            trades: 2,
            wins: 1,
            losses: 1,
            net_pnl_usd: 0.70,
        }
    );
}

#[test]
fn fill_summary_does_not_invent_missing_measurements() {
    let fills = vec![
        fill(Some(-2.0), Some(1_000), None),
        fill(Some(4.0), None, Some(3.0)),
    ];

    assert_eq!(
        summarize_fills(&fills),
        FillQuality {
            measured: 2,
            total_fees_usd: 0.02,
            mean_slippage_bps: Some(1.0),
            mean_ack_ms: Some(1_000.0),
            mean_markout_bps: Some(3.0),
        }
    );
}

#[test]
fn zero_trade_profit_factor_is_unavailable() {
    let summary = CohortTradePerformanceSummary::default();

    assert_eq!(profit_factor_label(&summary), "N/A");
}

#[test]
fn positive_sample_without_losses_reports_infinite_profit_factor() {
    let summary = CohortTradePerformanceSummary {
        closed_trades: 2,
        wins: 2,
        ..CohortTradePerformanceSummary::default()
    };

    assert_eq!(profit_factor_label(&summary), "∞");
}

#[test]
fn equity_path_excludes_prior_run_with_same_profile() {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.backend.run_id = Some("current-run".into());
    app.backend.cohort_checkpoint.trade_reflections = vec![
        profiled_trade("prior-run", 1.25),
        profiled_trade("current-run", -0.25),
    ];
    app.backend.cohort_checkpoint.trade_performance = Some(CohortTradePerformance {
        total: performance_summary(2, 1.0),
        current_profile: Some(CohortProfileTradePerformance {
            profile_fingerprint: "same-profile".into(),
            total: performance_summary(2, 1.0),
            ..CohortProfileTradePerformance::default()
        }),
        current_run: Some(CohortRunTradePerformance {
            run_id: "current-run".into(),
            total: performance_summary(1, -0.25),
            ..CohortRunTradePerformance::default()
        }),
        ..CohortTradePerformance::default()
    });

    let path = equity_path(&app);

    assert_eq!(path.trades.len(), 1);
    assert_eq!(path.total, -0.25);
}

fn profiled_trade(run_id: &str, pnl: f64) -> CohortTradeReflection {
    CohortTradeReflection {
        source_run_id: run_id.into(),
        source_profile_fingerprint: Some("same-profile".into()),
        net_pnl_usd: pnl,
        exit_venue_timestamp_ms: Some(1),
        ..CohortTradeReflection::default()
    }
}

fn performance_summary(closed: usize, pnl: f64) -> CohortTradePerformanceSummary {
    CohortTradePerformanceSummary {
        closed_trades: closed,
        wins: usize::from(pnl > 0.0),
        losses: usize::from(pnl < 0.0),
        net_pnl_usd: pnl,
        ..CohortTradePerformanceSummary::default()
    }
}
