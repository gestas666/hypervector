//! Read-only source-long forward outcome projection tests.

use std::fs;

use hypervector_tui::{
    App,
    backend_observer::parse_source_long_outcome,
    backend_telemetry::{BackendTelemetrySource, parse_backend_telemetry},
};
use ratatui::{Terminal, backend::TestBackend};

const OUTCOMES: &str = r#"{"event_type":"source_long_forward_outcome","observed_at_utc":"2026-07-31T14:00:00Z","execution_authority":"none","payload":{"observation_id":"2026-07-31T13:20:00+00:00|fade_td_eu","recipe_id":"fade_td_eu","status":"open","evidence_complete":true,"active_stream_gaps":0,"funding_evidence_gaps":0,"last_event_time_utc":"2026-07-31T13:59:59Z","counterfactual_initial_equity_usd":153.61,"portfolio_interaction":"independent_observer_not_shared_execution","report":{"final_equity":154.25,"submitted_entries":1,"entry_filled_quantity":0.025,"completed_trades":0,"open_positions":1,"maker_fees":0.24,"taker_fees":0.0,"funding_cashflow":-0.01,"liquidations":0}}}
{"event_type":"source_long_forward_outcome","observed_at_utc":"2026-07-31T14:05:00Z","execution_authority":"none","payload":{"observation_id":"2026-07-31T13:20:00+00:00|fade_td_eu","recipe_id":"fade_td_eu","status":"target_completed","evidence_complete":true,"active_stream_gaps":0,"funding_evidence_gaps":0,"last_event_time_utc":"2026-07-31T14:04:59Z","counterfactual_initial_equity_usd":153.61,"portfolio_interaction":"independent_observer_not_shared_execution","report":{"final_equity":154.92,"submitted_entries":1,"entry_filled_quantity":0.025,"completed_trades":1,"open_positions":0,"maker_fees":0.48,"taker_fees":0.0,"funding_cashflow":-0.01,"liquidations":0}}}"#;

#[test]
fn parses_latest_observe_only_outcome_with_costs() {
    let outcome = parse_source_long_outcome(OUTCOMES)
        .expect("valid outcome ledger")
        .expect("latest outcome");

    assert_eq!(outcome.recipe_id, "fade_td_eu");
    assert_eq!(outcome.status, "target_completed");
    assert!(outcome.evidence_complete);
    assert_eq!(outcome.initial_equity_usd, 153.61);
    assert_eq!(outcome.final_equity_usd, 154.92);
    assert_eq!(outcome.completed_trades, 1);
    assert_eq!(outcome.maker_fees_usd, 0.48);
    assert_eq!(outcome.funding_cashflow_usd, -0.01);
}

#[test]
fn parser_retries_only_an_unterminated_trailing_sidecar_append() {
    let content = format!("{OUTCOMES}\n{{\"event_type\":");

    let outcome = parse_source_long_outcome(&content)
        .expect("trailing append is in progress")
        .expect("latest complete outcome");

    assert_eq!(outcome.status, "target_completed");
}

#[test]
fn backend_source_refreshes_sidecar_when_execution_ledger_is_unchanged() {
    let temp = tempfile::tempdir().expect("tempdir");
    let backend = temp.path().join("decisions.jsonl");
    let outcomes = temp.path().join("source_long_outcomes.jsonl");
    fs::write(
        &backend,
        r#"{"run_id":"live","action":"session_start","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}"#,
    )
    .expect("backend ledger");
    let mut source = BackendTelemetrySource::with_observer_path(backend, outcomes.clone());

    let before = source.refresh();
    assert!(before.source_long_forward.is_none());

    fs::write(&outcomes, OUTCOMES).expect("outcome sidecar");
    let after = source.refresh();
    assert_eq!(
        after
            .source_long_forward
            .as_ref()
            .map(|outcome| outcome.status.as_str()),
        Some("target_completed")
    );
}

#[test]
fn dashboard_snapshot_defaults_to_no_forward_long_outcome() {
    let snapshot = parse_backend_telemetry(
        r#"{"run_id":"live","action":"session_start","strategy_name":"hypervelocity_source_follow_5m"}"#,
    )
    .expect("backend ledger");

    assert!(snapshot.source_long_forward.is_none());
}

#[test]
fn dashboard_labels_resolved_long_as_observer_not_execution() {
    let mut snapshot = parse_backend_telemetry(
        r#"{"run_id":"live","action":"session_start","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}
{"run_id":"live","action":"regime_observation","feed_ts":"2026-07-31T14:05:00Z","primary_regime":"RANGE","state_1m":"NOT_CLASSIFIED","state_5m":"RANGE","context_15m":"NOT_CLASSIFIED","mark_px":64000.0,"position_qty":0.0}"#,
    )
    .expect("backend ledger");
    snapshot.source_long_forward = parse_source_long_outcome(OUTCOMES).expect("outcome");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(snapshot);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw source-long outcome");

    let screen = rendered(&terminal);
    assert!(
        screen.contains("LONG OBS FADE_TD_EU TP Δ$+1.31 VALID"),
        "{screen}"
    );
    assert!(screen.contains("SHORT EXEC"), "{screen}");
}

fn rendered(terminal: &Terminal<TestBackend>) -> String {
    let buffer = terminal.backend().buffer();
    (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}
