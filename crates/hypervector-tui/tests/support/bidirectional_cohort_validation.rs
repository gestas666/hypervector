#[test]
fn legacy_cohort_ledger_never_turns_mark_samples_into_fake_candles() {
    let ledger = [identity(), snapshot(2, 100.0, false)].join("\n");
    let backend = parse_backend_telemetry(&format!("{ledger}\n")).expect("legacy fixture");
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);

    let screen = render(&mut app, 2, 120, 36);

    assert!(screen.contains("BACKEND OHLCV UNAVAILABLE"), "{screen}");
    assert!(!screen.contains("BACKEND REFERENCES"), "{screen}");
}

#[test]
fn first_candle_window_must_cover_every_enabled_symbol() {
    let mut candle_row: Value = serde_json::from_str(&market_candles()).expect("market candle row");
    candle_row["payload"]["bars"]
        .as_object_mut()
        .expect("bar map")
        .remove("HYPE");
    let ledger = [identity(), candle_row.to_string()].join("\n");

    let error = parse_backend_telemetry(&format!("{ledger}\n"))
        .expect_err("partial initial candle window must fail");

    assert!(
        error.to_string().contains("initial candle window"),
        "{error}"
    );
}

#[test]
fn provider_readiness_rejects_a_direction_that_disagrees_with_contract() {
    let mut routing_row: Value = serde_json::from_str(&routing()).expect("routing row");
    routing_row["payload"]["evaluations"][0]["readiness"]["side"] = json!("sideways");
    let ledger = [identity(), routing_row.to_string()].join("\n");

    let error = parse_backend_telemetry(&format!("{ledger}\n"))
        .expect_err("invalid readiness side must fail closed");

    assert!(
        error.to_string().contains("structurally invalid"),
        "{error}"
    );
}

#[test]
fn strategy_evidence_rejects_incomplete_provider_symbol_coverage() {
    let mut identity_row: Value = serde_json::from_str(&identity()).expect("identity row");
    identity_row["payload"]["strategy_evidence"]
        .as_array_mut()
        .expect("strategy evidence")
        .pop();

    let error = parse_backend_telemetry(&format!("{}\n", identity_row))
        .expect_err("partial research evidence must fail closed");

    assert!(
        error.to_string().contains("cover each provider-symbol"),
        "{error}"
    );
}

#[test]
fn provider_sizing_above_the_asset_adapter_ceiling_is_rejected() {
    let mut identity_row: Value = serde_json::from_str(&identity()).expect("identity row");
    identity_row["payload"]["providers"][1]["sizing_overrides"] = json!({
        "SOL": {
            "margin_fraction": 0.10,
            "max_notional_usd": 30.0
        }
    });

    let error = parse_backend_telemetry(&format!("{}\n", identity_row))
        .expect_err("provider sizing above the asset ceiling must fail closed");

    assert!(
        error
            .to_string()
            .contains("provider sizing scope is invalid"),
        "{error}"
    );
}

#[test]
fn source_follow_identity_rejects_an_invalid_symbol_contract() {
    let mut identity_row: Value = serde_json::from_str(&identity()).expect("identity row");
    identity_row["payload"]["providers"][2]["symbols"] = json!(["BTC", "SOL"]);
    let ledger = identity_row.to_string();

    let error = parse_backend_telemetry(&format!("{ledger}\n"))
        .expect_err("source-follow source contract must fail closed");

    assert!(
        error
            .to_string()
            .contains("source-follow provider contract"),
        "{error}"
    );
}

#[test]
fn hype_breakout_identity_rejects_an_invalid_timeframe_contract() {
    let mut identity_row: Value = serde_json::from_str(&identity()).expect("identity row");
    identity_row["payload"]["providers"][3]["timeframe"] = json!("5m");
    let ledger = identity_row.to_string();

    let error = parse_backend_telemetry(&format!("{ledger}\n"))
        .expect_err("HYPE breakout source contract must fail closed");

    assert!(
        error.to_string().contains("HT-Breakout provider contract"),
        "{error}"
    );
}

#[test]
fn breakout_v14_identity_accepts_cross_asset_execution_scope() {
    let mut identity_row: Value = serde_json::from_str(&identity()).expect("identity row");
    identity_row["payload"]["providers"][3]["symbols"] = json!(SYMBOLS);
    identity_row["payload"]["providers"][3]["execution_symbols"] = json!(SYMBOLS);
    let evidence = identity_row["payload"]["strategy_evidence"]
        .as_array_mut()
        .expect("strategy evidence");
    let template = evidence
        .iter()
        .find(|row| {
            row["strategy_id"] == "hype_breakout_onset_bidirectional_v1" && row["symbol"] == "HYPE"
        })
        .expect("HYPE evidence")
        .clone();
    for symbol in ["BTC", "ETH", "SOL"] {
        let mut row = template.clone();
        row["symbol"] = json!(symbol);
        evidence.push(row);
    }

    let backend =
        parse_backend_telemetry(&format!("{}\n", identity_row)).expect("cross-asset v14 identity");
    let provider = backend
        .cohort
        .providers
        .iter()
        .find(|row| row.strategy_id == "hype_breakout_onset_bidirectional_v1")
        .expect("breakout provider");

    assert_eq!(provider.symbols, SYMBOLS.map(str::to_string));
    assert_eq!(
        provider.execution_symbols,
        Some(SYMBOLS.map(str::to_string).to_vec())
    );
}

#[test]
fn unusable_terminal_gets_an_actionable_resize_message() {
    let mut app = cohort_app();
    let screen = render(&mut app, 0, 90, 25);
    assert!(screen.contains("TERMINAL TOO SMALL"), "{screen}");
    assert!(screen.contains("MINIMUM 100x28"), "{screen}");
}

#[test]
fn zero_equity_does_not_render_a_success_shaped_margin_ratio() {
    let ledger = [identity(), snapshot_with_equity(2, 100.0, false, 0.0)].join("\n");
    let backend = parse_backend_telemetry(&format!("{ledger}\n")).expect("zero-equity fixture");
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    let screen = render(&mut app, 0, 120, 36);
    assert!(screen.contains("MARGIN UTIL UNAVAILABLE"), "{screen}");
    assert!(!screen.contains("MARGIN UTIL 0.00%"), "{screen}");
}

#[test]
fn research_screen_separates_intents_actions_and_live_audit_health() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        analysis_mode: Some("live_execution".into()),
        readiness_evaluations: Some(4342),
        strategy_intents: Some(4),
        routing_actions: Some(1),
        eligible_signals: Some(4),
        live_audit_status: Some(CohortLiveAuditStatus {
            row_count: 8218,
            faults: 0,
            poll_cycles: 2520,
            poll_interval_count: 2519,
            poll_interval_mean_seconds: Some(15.433350780468439),
            poll_interval_median_seconds: Some(15.367621),
            poll_interval_minimum_seconds: Some(14.426317),
            poll_interval_maximum_seconds: Some(23.155777),
        }),
        ..CohortCheckpointTelemetry::default()
    };

    let screen = render(&mut app, 5, 160, 40);

    assert!(
        screen.contains("EVALUATIONS 4342  //  INTENTS 4  //  ACTIONS 1  //  ELIGIBLE 4"),
        "{screen}"
    );
    assert!(
        screen.contains(
            "AUDIT ROWS 8218 // POLLS 2520 // CADENCE 15.43s MED 15.37s [14.43s..23.16s] // FAULTS 0"
        ),
        "{screen}"
    );
}

fn render(app: &mut App, tab: usize, width: u16, height: u16) -> String {
    app.active_tab = tab;
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw cohort screen");
    rendered(&terminal)
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
