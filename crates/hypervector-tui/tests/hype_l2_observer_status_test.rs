use hypervector_tui::backend_hype_l2_observer::parse_hype_l2_observer_status;

#[test]
fn parses_running_scored_annotation_without_execution_authority() {
    let status = parse_hype_l2_observer_status(
        r#"{
            "schema_version":1,
            "mode":"hype_l2_ridge_prospective_observer_status",
            "state":"running",
            "execution_authority":"none",
            "report_only":true,
            "runtime_strategy_changed":false,
            "bundle":"data/models/hype_l2_ridge_observe_v1.json",
            "journal":"data/live/research/hype_l2_ridge_observations.jsonl",
            "polls":42,
            "durable_books_observed":317,
            "last_book_exchange_ts_ms":1785995321732,
            "latest_observation":{
                "status":"scored",
                "decision_time_ms":1785995280000,
                "side":"long",
                "predicted_gross_return_bps":12.5,
                "training_score_percentile":0.82,
                "score_band":"top_20pct_annotation",
                "bundle_sha256":"5f55f58f503cb4e31e6bf05b6d29f862a0bb215298aa642b0030c52cce1417b8",
                "execution_authority":"none",
                "report_only":true,
                "runtime_strategy_changed":false,
                "automatic_promotion":false,
                "coverage":{"books":59,"maximum_interval_ms":1100}
            },
            "outcome_summary":{
                "schema_version":1,
                "mode":"hype_l2_ridge_prospective_outcomes_v1",
                "status":"observed",
                "contract":{
                    "report_only":true,
                    "execution_authority":"none",
                    "runtime_strategy_changed":false,
                    "automatic_promotion":false,
                    "performance_gate":false
                },
                "counts":{
                    "observations":1,"scored":1,"coverage_unavailable":0,
                    "awaiting_entry_fill":0,"open":1,"resolved":0,"unreconciled":0
                },
                "latest_outcome":{
                    "status":"open","decision_time_ms":1785995280000,
                    "side":"long","score_band":"top_20pct_annotation",
                    "predicted_gross_return_bps":12.5,
                    "training_score_percentile":0.82,
                    "entry_trade_id":123,"entry_timestamp_ms":1785995290000,
                    "entry_price":55.0,"entry_size":1.0,
                    "actual_gross_return_bps":null,"actual_net_return_bps":null,
                    "marked_gross_return_bps":5.0,"marked_net_return_bps":3.0,
                    "marked_net_pnl_usd":0.0165,"fees_usd":0.02,"funding_usd":0.001,
                    "net_pnl_usd":null,"execution_authority":"none",
                    "report_only":true,"automatic_promotion":false
                },
                "resolved_performance":{
                    "resolved":0,"wins":0,"losses":0,"net_return_bps":null,
                    "mean_net_return_bps":null,"profit_factor":null
                },
                "confidence":"none_no_resolved_outcomes"
            },
            "updated_at_utc":"2026-08-06T05:49:01.998330+00:00"
        }"#,
    )
    .expect("valid observer status");

    assert!(status.available);
    assert_eq!(status.state.as_deref(), Some("running"));
    assert_eq!(status.durable_books_observed, Some(317));
    let observation = status.latest_observation.expect("scored observation");
    assert_eq!(observation.side.as_deref(), Some("long"));
    assert_eq!(observation.predicted_gross_return_bps, Some(12.5));
    assert_eq!(observation.coverage.books, Some(59));
    assert_eq!(observation.coverage.maximum_interval_ms, Some(1100));
    let outcomes = status.outcome_summary.expect("outcome summary");
    assert_eq!(outcomes.counts.expect("counts").open, 1);
    let outcome = outcomes.latest_outcome.expect("latest outcome");
    assert_eq!(outcome.status, "open");
    assert_eq!(outcome.marked_net_return_bps, Some(3.0));
}

#[test]
fn rejects_observer_status_that_claims_execution_authority() {
    let error = parse_hype_l2_observer_status(
        r#"{
            "schema_version":1,
            "mode":"hype_l2_ridge_prospective_observer_status",
            "state":"running",
            "execution_authority":"live",
            "report_only":false,
            "runtime_strategy_changed":true,
            "bundle":"bundle.json",
            "journal":"journal.jsonl",
            "polls":1,
            "durable_books_observed":1,
            "last_book_exchange_ts_ms":1785995321732,
            "latest_observation":null,
            "updated_at_utc":"2026-08-06T05:49:01+00:00"
        }"#,
    )
    .expect_err("execution-capable status must be rejected");

    assert!(error.contains("report-only contract"));
}
