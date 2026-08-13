#[test]
fn test_backend_timestamps_display_in_us_eastern_with_dst() {
    assert_eq!(
        hypervector_tui::ui::format_timestamp_display("2026-07-25T15:39:50.724000+00:00"),
        "2026-07-25 11:39:50 EDT"
    );
    assert_eq!(
        hypervector_tui::ui::format_timestamp_display("2026-01-25T15:39:50Z"),
        "2026-01-25 10:39:50 EST"
    );
    assert_eq!(
        hypervector_tui::ui::format_time_display("2026-07-25T15:39:50Z"),
        "11:39:50 EDT"
    );
}

fn make_snapshot(price: f64, high: f64, low: f64, state: RegimeState, ts: &str) -> RegimeSnapshot {
    RegimeSnapshot {
        timestamp_str: ts.to_string(),
        timestamp_ms: 1_784_850_000_000,
        price,
        open: Some(price),
        high,
        low,
        volume: 10.0,
        state,
        regime_reason: "fixture".into(),
        confidence: 0.6,
        regime_score_source: "fixture".into(),
        source_diagnostics: None,
        opi: 0.1,
        spread_bps: 1.2,
        bid_depth_ratio: 1.1,
        microstructure_source: "fixture".into(),
        bbwp_percentile: 50.0,
        rsi: 55.0,
        funding_zscore: 0.1,
        funding_source: "fixture".into(),
        trend_1m: "BULL".into(),
        trend_5m: "BULL".into(),
        trend_15m: "BULL".into(),
        long_weight: 2.0,
        short_weight: 0.0,
        max_leverage: 3.0,
        dynamic_leverage: 2.0,
        taker_allowed: false,
    }
}

fn render_rows(app: &App, width: u16, height: u16) -> Vec<String> {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw cockpit");
    let buffer = terminal.backend().buffer();
    (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect()
}

#[test]
fn screen_three_is_read_only_backend_chart_and_config_moves_to_four() {
    let mut snapshots = vec![
        make_snapshot(
            64_500.0,
            64_520.0,
            64_480.0,
            RegimeState::RangeChop,
            "2026-07-26T12:00:00Z",
        ),
        make_snapshot(
            64_540.0,
            64_560.0,
            64_490.0,
            RegimeState::BullMomentum,
            "2026-07-26T12:01:00Z",
        ),
    ];
    snapshots[0].open = Some(64_510.0);
    snapshots[1].open = Some(64_500.0);
    snapshots[1].bbwp_percentile = 20.0;
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.current_index = 1;
    app.active_tab = 2;
    app.backend.structural_direction = Some("long".into());
    app.backend.entry_direction = Some("long".into());
    app.backend.compression_ready = Some(true);
    app.backend.bbwp_compression_threshold = Some(25.0);
    app.backend.ema_gap_bps_signed = Some(2.0);
    app.backend.rsi_ema = Some(60.0);
    app.backend.rsi_cross_direction = Some("BK_UPWARD".into());
    app.backend.tactical_breakout_direction = Some("BK_UPWARD".into());
    app.backend.breakout_volume_ratio = Some(2.7);
    app.backend.prior_range_high = Some(64_560.0);
    app.backend.prior_range_low = Some(64_480.0);

    let chart = render_rows(&app, 180, 50).join("\n");
    assert!(chart.contains("[3] CHART"), "{chart}");
    assert!(chart.contains("[4] CONFIG"), "{chart}");
    assert!(chart.contains("BACKEND CANDLE TAPE"), "{chart}");
    assert!(chart.contains("CANDLES"), "{chart}");
    assert!(chart.contains("VOLUME"), "{chart}");
    assert!(chart.contains("REGIME TAPE"), "{chart}");
    assert!(chart.contains("STRATEGY LEVELS"), "{chart}");
    assert!(chart.contains("READ ONLY"), "{chart}");
    assert!(chart.contains("ENTRY ELIGIBILITY"), "{chart}");
    assert!(chart.contains("ELIGIBLE LONG"), "{chart}");
    assert!(chart.contains("STRUCT LONG"), "{chart}");
    assert!(chart.contains("SETUP UP"), "{chart}");
    assert!(chart.contains("BBWP READY"), "{chart}");
    assert!(chart.contains("RSI X UP"), "{chart}");
    assert!(chart.contains("VOL 2.70x"), "{chart}");
    assert!(chart.contains("R-HI $64560.00"), "{chart}");
    assert!(chart.contains("R-LO $64480.00"), "{chart}");
    assert!(!chart.contains("HIGH / LOW / MARK"), "{chart}");
    assert!(
        !chart.contains("EFFECTIVE BACKEND CONFIGURATION"),
        "{chart}"
    );

    app.active_tab = 3;
    let config = render_rows(&app, 180, 50).join("\n");
    assert!(
        config.contains("EFFECTIVE BACKEND CONFIGURATION"),
        "{config}"
    );

    app.active_tab = 2;
    let narrow_chart = render_rows(&app, 80, 24);
    assert_eq!(narrow_chart.len(), 24);

    app.snapshots[0].open = None;
    app.current_index = 0;
    let legacy = render_rows(&app, 180, 50).join("\n");
    assert!(legacy.contains("OPEN DATA UNAVAILABLE"), "{legacy}");

    app.active_tab = 3;
    app.toggle_tab();
    assert_eq!(app.active_tab, 0);
}

#[test]
fn regime_range_and_strength_gauges_are_compact_red_and_purple() {
    let snapshots = vec![make_snapshot(
        64_500.0,
        64_520.0,
        64_480.0,
        RegimeState::RangeChop,
        "2026-07-26T12:00:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.active_tab = 1;
    app.backend.compression_ready = Some(true);
    app.backend.bbwp_compression_threshold = Some(25.0);

    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw regime screen");
    let buffer = terminal.backend().buffer();
    let rows = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>();
    assert!(rows.join("\n").contains("BBWP <25.0% READY"));

    let (range_y, range_x) = rows
        .iter()
        .enumerate()
        .find_map(|(y, row)| {
            row.find("60B PRICE RANGE")
                .map(|byte| (y, row[..byte].chars().count()))
        })
        .expect("compact price-range title");
    let (strength_y, strength_x) = rows
        .iter()
        .enumerate()
        .find_map(|(y, row)| {
            row.find("REGIME STRENGTH")
                .map(|byte| (y, row[..byte].chars().count()))
        })
        .expect("compact regime-strength title");

    assert_eq!(
        buffer[(range_x as u16, range_y as u16)].fg,
        Color::Rgb(255, 45, 85)
    );
    assert_eq!(
        buffer[(strength_x as u16, strength_y as u16)].fg,
        Color::Rgb(190, 80, 255)
    );
    let rendered = rows.join("\n");
    assert!(!rendered.contains("PRICE ACTION RANGE TRAJECTORY"));
    assert!(!rendered.contains("STRUCTURE STRENGTH - REPORT ONLY"));
}

#[test]
fn live_scan_status_breathes_without_ascii_chevrons() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-26T12:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_UP","mark_px":100.0,"high":101.0,"low":99.0,"volume":5.0,"entry_allowed":false}
{"feed_ts":"2026-07-26T12:00:05Z","action":"book_observation","run_id":"hv","source":"hl_rest_l2","recv_ts_ms":1785067205000.0,"mid_px":100.0,"spread_bps":1.0,"bid_depth_ratio":1.0,"opi":0.0,"bids":[{"price":99.5,"size":1.0}],"asks":[{"price":100.5,"size":1.0}]}"#,
    )
    .expect("fresh backend telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.book_state.age_ms = 10.0;

    app.tick_count = 0;
    let contracted = render_rows(&app, 180, 50).join("\n");
    app.tick_count = 6;
    let expanded = render_rows(&app, 180, 50).join("\n");

    assert!(contracted.contains("· SCANNING LIVE ·"), "{contracted}");
    assert!(expanded.contains("◀ SCANNING LIVE ▶"), "{expanded}");
    assert!(!contracted.contains("<> SCANNING LIVE <>"));
}

#[test]
fn screen_two_places_context_directly_below_canonical_primary() {
    let snapshots = vec![make_snapshot(
        64_500.0,
        64_510.0,
        64_490.0,
        RegimeState::BullMomentum,
        "2026-07-26T12:00:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.active_tab = 1;

    let rows = render_rows(&app, 120, 50);
    let canonical_row = rows
        .iter()
        .position(|row| row.contains("Canonical Primary:"))
        .expect("canonical primary row");
    let context_row = rows
        .iter()
        .position(|row| row.contains("Context Only: 15m [BULL]"))
        .expect("context-only row");

    assert_eq!(context_row, canonical_row + 1);
    let rendered = rows.join("\n");
    assert!(rendered.contains("5m authoritative"), "{rendered}");
    assert!(rendered.contains("Structure Strength"), "{rendered}");
    assert!(!rendered.contains("1m directional fallback"), "{rendered}");
    assert!(!rendered.contains("Model Conviction"), "{rendered}");
}

#[test]
fn screen_two_compacts_the_backend_strength_source_label() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0}
{"feed_ts":"2026-07-26T12:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_UP","regime_strength_score":0.53,"regime_score_source":"mean_multitimeframe_ema_gap_strength_percentile_rank","mark_px":100.0,"high":101.0,"low":99.0,"volume":5.0}"#,
    )
    .expect("strength-source telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 1;

    let rendered = render_rows(&app, 180, 50).join("\n");

    assert!(
        rendered.contains("Source: MTF EMA-GAP PCTL RANK"),
        "{rendered}"
    );
    assert!(
        !rendered.contains("mean_multitimeframe_ema_gap_strength_percentile_rank"),
        "{rendered}"
    );
}

#[test]
fn active_position_preserves_negative_unrealized_pnl_sign() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-26T12:00:00Z","action":"enter_long","run_id":"hv","symbol":"BTC","fill_px":100.0,"fill_qty":1.0,"position_qty":1.0,"position_avg_px":100.0,"equity":9998.5,"realized_pnl":-1.5,"unrealized_pnl":0.0,"fee_usd":1.5,"leverage":40.0}
{"feed_ts":"2026-07-26T12:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","mark_px":99.0,"position_qty":1.0,"position_avg_px":100.0,"equity":9997.5,"realized_pnl":-1.5,"unrealized_pnl":-1.0}"#,
    )
    .expect("negative unrealized telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);

    let rendered = render_rows(&app, 180, 50).join("\n");

    assert!(rendered.contains("U/PNL -1.00"), "{rendered}");
}

#[test]
fn test_regime_cockpit_app_state() {
    let snapshots = generate_synthetic_history(100);
    assert_eq!(snapshots.len(), 100);

    let mut app = App::new("BTC".into(), "5m".into(), snapshots, false, true);

    assert_eq!(app.symbol, "BTC");
    assert_eq!(app.timeframe, "5m");
    assert_eq!(app.current_index, 0);

    let initial_snap = app.current_snapshot();
    assert_eq!(initial_snap.state, RegimeState::BullMomentum);
    assert!(app.book_state.bid_levels.is_empty());
    assert!(app.book_state.ask_levels.is_empty());
    assert!(!app.book_state.gate_ok);

    // Test playback navigation
    app.step_forward();
    assert_eq!(app.current_index, 1);

    app.step_backward();
    assert_eq!(app.current_index, 0);

    // Test speed cycling
    app.cycle_speed();
    assert_eq!(app.playback_speed, 2.0);

    // Test timeframe cycling
    app.cycle_timeframe();
    assert_eq!(app.timeframe, "15m");
}

#[test]
fn test_parse_snapshot_json_uses_real_fields() {
    let val = serde_json::json!({
        "timestamp_str": "2026-07-21 11:45:00 UTC",
        "timestamp_ms": 1_784_634_300_000_u64,
        "open": 66300.0,
        "close": 66311.0,
        "high": 66320.0,
        "low": 66290.0,
        "volume": 12.4,
        "regime_state": "TREND_DOWN",
        "confidence": 0.61,
        "opi": -0.22,
        "spread_bps": 2.4,
        "bid_depth_ratio": 0.85,
        "bbwp_percentile": 33.3,
        "rsi": 41.2,
        "funding_zscore": -0.7,
        "trend_1m": "BEAR",
        "trend_5m": "BEAR",
        "trend_15m": "BULL",
        "long_weight": 0.0,
        "short_weight": 2.0,
        "max_leverage": 3.0,
        "dynamic_leverage": 1.75,
        "taker_allowed": true
    });

    let snap = parse_snapshot_json(&val, 7).expect("snapshot should parse");
    assert_eq!(snap.timestamp_ms, 1_784_634_300_000);
    assert_eq!(snap.state, RegimeState::BearMomentum);
    assert_eq!(snap.open, Some(66300.0));
    assert!((snap.price - 66311.0).abs() < 1e-9);
    assert!((snap.high - 66320.0).abs() < 1e-9);
    assert!((snap.low - 66290.0).abs() < 1e-9);
    assert!((snap.confidence - 0.61).abs() < 1e-9);
    assert!((snap.opi - (-0.22)).abs() < 1e-9);
    assert!((snap.spread_bps - 2.4).abs() < 1e-9);
    assert!((snap.bid_depth_ratio - 0.85).abs() < 1e-9);
    assert!((snap.bbwp_percentile - 33.3).abs() < 1e-9);
    assert!((snap.rsi - 41.2).abs() < 1e-9);
    assert!((snap.funding_zscore - (-0.7)).abs() < 1e-9);
    assert_eq!(snap.trend_1m, "BEAR");
    assert_eq!(snap.trend_15m, "BULL");
    assert!((snap.short_weight - 2.0).abs() < 1e-9);
    assert!((snap.dynamic_leverage - 1.75).abs() < 1e-9);
    assert!(snap.taker_allowed);
}

#[test]
fn test_parse_snapshot_json_recognizes_canonical_trend_up() {
    let val = serde_json::json!({
        "timestamp_str": "2026-07-25 13:16:00 UTC",
        "close": 64113.0,
        "regime_state": "TREND_UP"
    });

    assert!(parse_snapshot_json(&val, 0).is_none());
}

#[test]
fn backend_exposes_regime_policy_and_non_model_strength_score() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","regime_policy":{"execution_timeframe":"1m","primary_timeframe":"5m","context_timeframe":"15m","context_is_hard_gate":false,"allowed_entry_states":["TREND_UP","TREND_DOWN","BREAKOUT"],"blocked_entry_states":["RANGE","TRANSITION","UNKNOWN"],"breakout_requires_direction":true,"confidence_is_gate":false}}
{"feed_ts":"2026-07-26T12:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","regime_strength_score":0.73,"regime_score_source":"mean_multitimeframe_ema_gap_strength_percentile_rank","mark_px":100.0,"high":101.0,"low":99.0,"volume":5.0,"state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","regime_reason":"5m_primary_trend"}"#,
    )
    .expect("regime telemetry");

    assert_eq!(telemetry.regime_policy["primary_timeframe"], "5m");
    assert_eq!(telemetry.latest_regime_strength_score, Some(0.73));
    assert_eq!(
        telemetry.latest_regime_score_source.as_deref(),
        Some("mean_multitimeframe_ema_gap_strength_percentile_rank")
    );
}

#[test]
fn test_snapshot_playback_never_creates_authoritative_trades() {
    // Bars 0-4 chop, bull transition at bar 5 (entry 100.0), TP barrier at
    // 100.2 (8% margin at 40x = 0.2% price move) crossed on bar 7.
    let mut snaps: Vec<RegimeSnapshot> = Vec::new();
    for i in 0..5 {
        snaps.push(make_snapshot(
            100.0,
            100.02,
            99.98,
            RegimeState::RangeChop,
            &format!("2026-07-21 11:0{} :00 UTC", i),
        ));
    }
    snaps.push(make_snapshot(
        100.0,
        100.05,
        99.97,
        RegimeState::BullMomentum,
        "2026-07-21 11:05:00 UTC",
    ));
    snaps.push(make_snapshot(
        100.1,
        100.15,
        100.0,
        RegimeState::BullMomentum,
        "2026-07-21 11:06:00 UTC",
    ));
    snaps.push(make_snapshot(
        100.22,
        100.25,
        100.05,
        RegimeState::BullMomentum,
        "2026-07-21 11:07:00 UTC",
    ));
    snaps.push(make_snapshot(
        100.2,
        100.24,
        100.1,
        RegimeState::BullMomentum,
        "2026-07-21 11:08:00 UTC",
    ));

    let mut app = App::new("BTC".into(), "1m".into(), snaps, false, true);

    // Regime snapshots are display telemetry, never an execution source.
    assert!(app.hv_trades.is_empty());
    assert!(app.paper_trades.is_empty());
    assert_eq!(app.paper_stats.total_trades, 0);
    assert!(!app.active_position.is_active());

    // Moving the playhead must not manufacture paper trades.
    app.current_index = app.snapshots.len() - 1;
    app.refresh_playhead_state();

    assert!(app.hv_trades.is_empty());
    assert!(app.paper_trades.is_empty());
    assert_eq!(app.paper_stats.total_trades, 0);
    assert!(!app.active_position.is_active());
}
