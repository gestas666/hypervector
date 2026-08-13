#[test]
fn measured_open_position_shows_exposure_target_and_liquidation_distance() {
    let ledger = format!(
        "{MEASURED_LEDGER}\n{}\n{}",
        r#"{"feed_ts":"2026-08-02T12:05:01Z","action":"enter_long","run_id":"measured","symbol":"BTC","fill_px":64000.0,"fill_qty":0.1171875,"position_qty":0.1171875,"position_avg_px":64000.0,"mark_px":64100.0,"liquidation_price":52000.0,"leverage":5.0,"fee_usd":1.125,"equity":15010.59,"realized_pnl":-1.125,"unrealized_pnl":11.71875}"#,
        r#"{"feed_ts":"2026-08-02T12:05:02Z","action":"entry_execution_observation","run_id":"measured","mark_px":64100.0,"active_target_prices":[64171.0]}"#,
    );
    let telemetry = parse_backend_telemetry(&ledger).expect("measured open telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw measured open position");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("MARK  $64100.00"), "{dashboard}");
    assert!(
        dashboard.contains("MARGIN $1500.00 | NOTIONAL $7500.00"),
        "{dashboard}"
    );
    assert!(dashboard.contains("TP $64171.00"), "{dashboard}");
    assert!(dashboard.contains("LIQ DIST 18.88%"), "{dashboard}");
    assert!(dashboard.contains("ISOLATED"), "{dashboard}");

    let compact_backend = TestBackend::new(120, 36);
    let mut compact_terminal = Terminal::new(compact_backend).expect("compact terminal");
    compact_terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw compact measured open position");
    let compact = rendered(&compact_terminal);
    assert!(compact.contains("U/PNL +11.72"), "{compact}");
    assert!(compact.contains("TP $64171.00"), "{compact}");
    assert!(compact.contains("LIQ $52000.00 (18.88%)"), "{compact}");
    assert!(compact.contains("MARGIN $1500.00"), "{compact}");
}

#[test]
fn measured_source_config_exposes_price_target_and_evidence_provenance() {
    let telemetry = parse_backend_telemetry(MEASURED_LEDGER).expect("measured telemetry");
    let rows = backend_config_rows(&telemetry);

    assert!(
        rows.iter()
            .any(|row| { row.option == "Gross notional / equity" && row.value == "0.50x" })
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Target price move" && row.value == "26.7 bps")
    );
    assert!(rows.iter().any(|row| {
        row.option == "Evidence status" && row.value == "development / not live proven"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Execution economics" && row.value == "inconclusive" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Active book-gap windows" && row.value == "2" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Metalabel observation" && row.value == "annotation_collection"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Metalabel inference" && row.value == "inactive" })
    );
}

#[test]
fn measured_config_scrolls_to_selection_and_expands_full_value() {
    let telemetry = parse_backend_telemetry(MEASURED_LEDGER).expect("measured telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 3;
    let rows = backend_config_rows(&app.backend);
    app.config.selected_option_index = rows
        .iter()
        .position(|row| row.option == "Evidence status")
        .expect("evidence row");
    let backend = TestBackend::new(120, 36);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw selected evidence row");
    let evidence = rendered(&terminal);
    assert!(evidence.contains("Evidence status"), "{evidence}");
    assert!(
        evidence.contains("SELECTED Evidence / Evidence status = development / not live proven"),
        "{evidence}"
    );

    app.config.selected_option_index = rows.len() - 1;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw final config row");
    let last = rendered(&terminal);
    assert!(
        last.contains(&rows.last().expect("last row").option),
        "{last}"
    );
}

#[test]
fn measured_secondary_screens_retain_truth_at_acceptance_sizes() {
    for (width, height) in [(120, 36), (180, 52)] {
        let telemetry = parse_backend_telemetry(MEASURED_LEDGER).expect("measured telemetry");
        let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
        app.apply_backend_telemetry(telemetry);

        app.active_tab = 1;
        let regime = render_at(&app, width, height);
        if width == 120 {
            assert!(regime.contains("5m/60s"), "{regime}");
        }
        assert!(regime.contains("5m SOURCE ENTRY AUTHORITY"), "{regime}");
        assert!(regime.contains("BIDIRECTIONAL EXECUTION"), "{regime}");
        assert!(regime.contains("SOURCE CONFIDENCE 82.0%"), "{regime}");
        assert!(
            regime.contains("SOURCE READINESS SIGNAL OBSERVED"),
            "{regime}"
        );
        assert!(!regime.contains("SOURCE READINESS WAIT"), "{regime}");
        assert!(regime.contains("L2 ORDERBOOK NOT AVAILABLE"), "{regime}");
        assert!(!regime.contains("BBWP"), "{regime}");

        app.active_tab = 2;
        let chart = render_at(&app, width, height);
        assert!(chart.contains("CANDLES · BACKEND OHLC"), "{chart}");
        assert!(chart.contains("CONF 82.0%"), "{chart}");
        assert!(chart.contains("RANGE 18.0 bps"), "{chart}");
        assert!(chart.contains("TARGET 1.33% GROSS MARGIN"), "{chart}");

        app.active_tab = 3;
        let rows = backend_config_rows(&app.backend);
        app.config.selected_option_index = rows
            .iter()
            .position(|row| row.option == "Evidence status")
            .expect("evidence row");
        let config = render_at(&app, width, height);
        assert!(config.contains("Evidence status"), "{config}");
        assert!(config.contains("development / not live proven"), "{config}");

        if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
            println!("--- measured {width}x{height} regime ---\n{regime}");
            println!("--- measured {width}x{height} chart ---\n{chart}");
            println!("--- measured {width}x{height} config ---\n{config}");
        }
    }
}

#[test]
fn source_chart_does_not_turn_missing_readiness_into_measured_zeroes() {
    let ledger = r#"{"run_id":"missing","action":"session_start","feed_ts":"session_start","strategy_name":"hypervelocity_source_follow_5m","execution_mode":"shadow","strategy_params":{"leverage":5.0},"risk":{"margin_fraction":0.1,"notional_fraction":0.5},"exits":{"target_margin_pct":1.3333333333333333,"target_price_fraction":0.0026666666666666666,"maximum_hold_seconds":86400.0,"fixed_stop":"none"},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","side":"bidirectional","minimum_confidence":0.7,"minimum_completed_5m_range_bps":12.0,"maximum_completed_5m_range_bps":100.0}}
{"run_id":"missing","action":"regime_history","feed_ts":"2026-08-02T12:00:00Z","primary_regime":"RANGE","state_5m":"RANGE","mark_px":64000.0,"open":63990.0,"high":64010.0,"low":63980.0,"close":64000.0,"volume":10.0}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("missing readiness telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 2;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw source chart");
    let chart = rendered(&terminal);
    assert!(chart.contains("CONF N/A"), "{chart}");
    assert!(chart.contains("RANGE N/A"), "{chart}");
    assert!(!chart.contains("CONF 0.0%"), "{chart}");
    assert!(!chart.contains("RANGE 0.0 bps"), "{chart}");
}

const MEASURED_LEDGER: &str = r#"{"feed_ts":"session_start","action":"session_start","run_id":"measured","profile_id":"hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow_v1","strategy_name":"hypervelocity_source_follow_5m","execution_mode":"shadow","metalabel_mode":"observe","metalabel_policy":{"observation_type":"annotation_collection","inference_active":false,"bundle_id":null,"probabilities_emitted":false,"may_filter":false,"may_scale":false,"execution_authority":"none"},"strategy_params":{"leverage":5.0,"target_margin_pct":1.3333333333333333},"position_policy":{"position_mode":"one_way","max_positions_per_symbol":1},"risk":{"margin_fraction":0.1,"notional_fraction":0.5},"exits":{"target_margin_pct":1.3333333333333333,"target_price_fraction":0.0026666666666666666,"target_basis":"gross_margin_return_before_costs","fixed_stop":"none","maximum_hold_seconds":86400.0,"range_policy":"hold_until_target_or_maximum_hold"},"execution":{"order_type":"limit","time_in_force":"post_only","maximum_hold_exit":"first_fresh_bbo_taker","execution_authority":"shadow_only"},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","side":"bidirectional","primary_timeframe":"5m","context_timeframe":"15m","state_1m_role":"not_classified","context_role":"not_classified","minimum_confidence":0.7,"minimum_completed_5m_range_bps":12.0,"maximum_completed_5m_range_bps":100.0,"entry_pulse_seconds":60.0},"runtime":{"evidence_status":"development_candidate_not_live_proven","execution_economics_conclusive":false,"active_book_gap_windows":2},"init_cash":15000.0,"equity":15000.0,"position_qty":0.0}
{"feed_ts":"2026-08-02T12:05:00Z","action":"regime_observation","run_id":"measured","primary_regime":"TREND_UP","state_1m":"NOT_CLASSIFIED","state_5m":"TREND_UP","context_15m":"NOT_CLASSIFIED","confidence":0.82,"source_follow_signal_range_bps":18.0,"entry_direction":"long","entry_allowed":true,"decision_action":"enter_long","regime_reason":"source_follow_entry_pulse","mark_px":64000.0,"open":63950.0,"high":64020.0,"low":63920.0,"close":64000.0,"volume":100.0}"#;

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

fn render_at(app: &App, width: u16, height: u16) -> String {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw acceptance screen");
    rendered(&terminal)
}
