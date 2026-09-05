use hypervector_tui::backend_cohort_checkpoint::CohortCheckpointTelemetry;
use hypervector_tui::backend_cohort_portfolio_archive::{
    CohortAccountingEpoch, CohortPortfolioArchive,
};
use hypervector_tui::backend_cohort_trade_performance::{
    CohortAllTimeTradePerformance, CohortTradePerformance, CohortTradePerformanceSummary,
};

fn performance(closed_trades: usize, net_pnl_usd: f64) -> CohortAllTimeTradePerformance {
    CohortAllTimeTradePerformance {
        total: CohortTradePerformanceSummary {
            closed_trades,
            net_pnl_usd,
            ..CohortTradePerformanceSummary::default()
        },
        ..CohortAllTimeTradePerformance::default()
    }
}

#[test]
fn fresher_reflections_temporarily_outrank_a_lagging_archive() {
    let checkpoint = CohortCheckpointTelemetry {
        portfolio_archive: Some(CohortPortfolioArchive {
            symbols: vec!["BTC".into()],
            observed_through_utc: Some("2026-08-12T13:44:00+00:00".into()),
            performance: performance(63, -1.92),
            accounting_epoch: None,
            preserved_history: None,
        }),
        trade_performance: Some(CohortTradePerformance {
            all_time_live: Some(performance(64, -1.75)),
            ..CohortTradePerformance::default()
        }),
        ..CohortCheckpointTelemetry::default()
    };

    let selected = checkpoint.all_time_performance().expect("all-time history");

    assert_eq!(selected.total.closed_trades, 64);
    assert_eq!(selected.total.net_pnl_usd, -1.75);
}

#[test]
fn accounting_epoch_archive_outranks_preserved_prior_reflections() {
    let checkpoint = CohortCheckpointTelemetry {
        portfolio_archive: Some(CohortPortfolioArchive {
            symbols: vec!["BTC".into()],
            observed_through_utc: None,
            performance: performance(0, 0.0),
            accounting_epoch: Some(CohortAccountingEpoch {
                epoch_id: "v51_first_live".into(),
                profile_fingerprint: "a".repeat(64),
                start_venue_timestamp_ms: 1_786_648_891_318,
                included_profile_fingerprints: Vec::new(),
            }),
            preserved_history: Some(
                hypervector_tui::backend_cohort_portfolio_archive::CohortPreservedHistory {
                    symbols: vec!["BTC".into()],
                    observed_through_utc: None,
                    performance: performance(73, 4.24),
                },
            ),
        }),
        trade_performance: Some(CohortTradePerformance {
            all_time_live: Some(performance(73, 4.24)),
            ..CohortTradePerformance::default()
        }),
        ..CohortCheckpointTelemetry::default()
    };

    let selected = checkpoint.all_time_performance().expect("epoch history");

    assert_eq!(selected.total.closed_trades, 0);
    assert_eq!(selected.total.net_pnl_usd, 0.0);
}
