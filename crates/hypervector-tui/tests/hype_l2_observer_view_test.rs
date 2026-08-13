use hypervector_tui::backend_hype_l2_observer::{
    HypeL2CoverageTelemetry, HypeL2ObservationTelemetry, HypeL2ObserverTelemetry,
};
use hypervector_tui::cohort_hype_l2_observer::summary_text;

#[test]
fn warm_observer_is_not_rendered_as_a_zero_score() {
    let status = HypeL2ObserverTelemetry {
        configured: true,
        available: true,
        state: Some("running".into()),
        durable_books_observed: Some(317),
        last_book_exchange_ts_ms: Some(1_785_995_321_732),
        ..HypeL2ObserverTelemetry::default()
    };

    let text = summary_text(&status, 1_785_995_323_000).join("\n");

    assert!(text.contains("317 BOOKS"));
    assert!(text.contains("BOOK 1.3s"));
    assert!(text.contains("WARM / WAITING FUTURE HYPE ENTRY"));
    assert!(!text.contains("0.00bps"));
}

#[test]
fn latest_score_reports_prediction_percentile_and_coverage() {
    let status = HypeL2ObserverTelemetry {
        configured: true,
        available: true,
        state: Some("running".into()),
        durable_books_observed: Some(400),
        last_book_exchange_ts_ms: Some(1_785_995_321_732),
        latest_observation: Some(HypeL2ObservationTelemetry {
            status: "scored".into(),
            decision_time_ms: 1_785_995_280_000,
            side: Some("long".into()),
            predicted_gross_return_bps: Some(12.5),
            training_score_percentile: Some(0.82),
            score_band: Some("top_20pct_annotation".into()),
            reason: None,
            bundle_sha256: None,
            coverage: HypeL2CoverageTelemetry {
                books: Some(59),
                maximum_interval_ms: Some(1100),
                ..HypeL2CoverageTelemetry::default()
            },
            execution_authority: Some("none".into()),
            report_only: Some(true),
            runtime_strategy_changed: Some(false),
            automatic_promotion: Some(false),
        }),
        ..HypeL2ObserverTelemetry::default()
    };

    let text = summary_text(&status, 1_785_995_323_000).join("\n");

    assert!(text.contains("LATEST LONG +12.50bps"));
    assert!(text.contains("TRAIN P82"));
    assert!(text.contains("COV 59 / GAP 1100ms"));
    assert!(text.contains("ANNOTATION ONLY"));
}

#[test]
fn missing_status_is_unavailable_instead_of_numerically_empty() {
    let text = summary_text(&HypeL2ObserverTelemetry::default(), 0).join("\n");

    assert!(text.contains("NOT CONFIGURED"));
    assert!(text.contains("NO EXECUTION AUTHORITY"));
    assert!(!text.contains("BOOKS 0"));
}
