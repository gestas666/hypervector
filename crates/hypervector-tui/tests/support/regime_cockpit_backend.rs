#[test]
fn test_app_applies_backend_telemetry_and_keeps_config_read_only() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper_long","execution_mode":"shadow","metalabel_mode":"observe","init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"enter_long","run_id":"hv","strategy_name":"hypervelocity_1m_scalper_long","symbol":"BTC","fill_px":100.0,"fill_qty":0.1,"position_qty":0.1,"position_avg_px":100.0,"equity":9998.0,"realized_pnl":-2.0,"unrealized_pnl":1.0,"conviction_source":"metalabel_observe","metalabel_p":0.62,"metalabel_bundle_id":"hypervelocity-long-v001"}"#,
    )
    .expect("telemetry");
    let snapshots = vec![make_snapshot(
        100.0,
        100.1,
        99.9,
        RegimeState::BullMomentum,
        "2026-07-25 12:00:00 UTC",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);

    app.apply_backend_telemetry(telemetry);

    assert!(app.active_position.is_active());
    assert_eq!(app.active_position.direction, "LONG");
    assert_eq!(app.paper_stats.current_equity, 9998.0);
    assert_eq!(app.backend.latest_metalabel_p, Some(0.62));
    let config_before = app.config.clone();
    app.toggle_config_option();
    app.increase_config_value();
    app.decrease_config_value();
    assert_eq!(app.config, config_before);
    assert_eq!(app.paper_stats.current_equity, 9998.0);
}

#[test]
fn test_display_fallback_matches_fixed_backend_contract() {
    let config = EngineConfig::default();

    assert_eq!(config.static_leverage_value, 30.0);
    assert_eq!(config.margin_tp_pct, 8.0);
    assert_eq!(config.margin_sl_pct, 0.0);
    assert_eq!(config.equity_risk_frac, 0.70);
    assert_eq!(config.split_position_mode, SplitPositionMode::None);
}

#[test]
fn test_live_app_follows_backend_regimes_transitions_and_book() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0}
{"feed_ts":"2026-07-25T14:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_UP","confidence":0.60,"regime_reason":"range","mark_px":100.0,"high":101.0,"low":99.0,"volume":12.0}
{"feed_ts":"2026-07-25T14:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","confidence":0.80,"regime_reason":"trend","mark_px":101.0,"high":102.0,"low":100.0,"volume":15.0}
{"feed_ts":"2026-07-25T14:01:05Z","action":"book_observation","run_id":"hv","source":"hl_rest_l2","exchange_ts_ms":1784988065000.0,"recv_ts_ms":1784988065050.0,"mid_px":101.25,"spread_bps":4.9,"bid_depth_ratio":2.0,"opi":0.33,"bids":[{"price":101.0,"size":4.0}],"asks":[{"price":101.5,"size":2.0}]}"#,
    )
    .expect("telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);

    app.apply_backend_telemetry(telemetry);

    assert_eq!(app.snapshots.len(), 2);
    assert_eq!(app.current_index, 1);
    assert_eq!(app.events.len(), 1);
    assert_eq!(app.events[0].from_state, RegimeState::RangeChop);
    assert_eq!(app.events[0].to_state, RegimeState::BullMomentum);
    assert_eq!(app.events[0].trigger_reason, "trend");
    assert!((app.book_state.spread_bps - 4.9).abs() < 1e-9);
    assert_eq!(app.book_state.bid_levels[0].price, 101.0);

    app.on_tick();
    assert_eq!(app.current_index, 1);
    assert_eq!(app.book_state.bid_levels.len(), 1);
    assert_eq!(app.book_state.bid_levels[0].price, 101.0);
}

#[test]
fn test_live_app_does_not_invent_book_when_backend_has_none() {
    let snapshots = vec![make_snapshot(
        100.0,
        101.0,
        99.0,
        RegimeState::RangeChop,
        "2026-07-25T14:00:00Z",
    )];
    let app = App::new("BTC".into(), "1m".into(), snapshots, true, false);

    assert!(app.book_state.bid_levels.is_empty());
    assert!(app.book_state.ask_levels.is_empty());
    assert!(!app.book_state.gate_ok);
}

#[test]
fn disconnected_backend_does_not_invent_default_account_equity() {
    let app = App::new("BTC".into(), "1m".into(), vec![], true, false);

    let screen = render_rows(&app, 120, 24).join("\n");

    assert!(screen.contains("equity=not reported"), "{screen}");
    assert!(!screen.contains("equity=$10000.00"), "{screen}");
}

#[test]
fn test_backend_config_is_a_selectable_menu_not_raw_json() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","data_root":"/tmp/hyper vector's data","metalabel_mode":"off","strategy_params":{"leverage":40.0,"target_margin_pct":8.0},"position_policy":{"position_mode":"one_way","max_positions_per_symbol":1},"regime_policy":{"execution_timeframe":"1m","primary_timeframe":"5m","context_timeframe":"15m","context_is_hard_gate":false,"entry_trigger":"5m_structure_or_confirmed_breakout","tactical_setup":"bbwp_rsi_breakout_annotation","tactical_setup_is_gate":false,"ema_fast":21,"ema_slow":55,"structure_lookback":240,"minimum_trend_gap_bps":1.0,"range_filter":"bbwp_compression","bbwp_length":20,"bbwp_lookback":240,"bbwp_compression_threshold":25.0,"rsi_length":14,"rsi_signal_length":7,"breakout_lookback":90,"breakout_clearance_bps":8.0,"breakout_volume_lookback":20,"breakout_volume_multiple":2.5,"allowed_entry_states":["TREND_UP","TREND_DOWN","BREAKOUT"],"blocked_entry_states":["RANGE","TRANSITION","UNKNOWN"],"breakout_requires_direction":true,"confidence_is_gate":false},"risk":{"margin_fraction":0.7},"exits":{"target_margin_pct":8.0,"range_policy":"hold_until_target"},"execution":{"order_type":"limit","time_in_force":"post_only","entry_ttl_seconds":300.0,"same_direction_reentry_policy":"regime_reset"},"costs":{"maker_fee_rate":0.00015,"funding_source":"live_meta_and_asset_contexts"},"init_cash":10000.0,"equity":10000.0}"#,
    )
    .expect("telemetry");

    let rows = backend_config_rows(&telemetry);

    assert!(rows.len() >= 10);
    assert!(
        rows.iter()
            .any(|row| row.option == "Leverage" && row.value == "40.0x")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Margin allocation" && row.value == "70.0%")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Position mode" && row.value == "one_way")
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Same-side re-entry" && row.value == "regime_reset" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Primary regime timeframe" && row.value == "5m" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Blocked entry states" && row.value == "RANGE, TRANSITION, UNKNOWN"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "EMA pair" && row.value == "21 / 55" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Range filter" && row.value == "bbwp_compression" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Tactical setup" && row.value == "bbwp_rsi_breakout_annotation"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Tactical setup gate" && row.value == "false" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "BBWP compression" && row.value == "<25.0%" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Breakout clearance" && row.value == "8.0 bps" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Breakout volume" && row.value == "2.50x / 20 bars" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Shadow reset"
            && row.value == "explicit CLI only"
            && row.source
                == "uv run python -m hypervector --data-root '/tmp/hyper vector'\"'\"'s data' hypervelocity-shadow-reset --yes"
    }));
    assert!(rows.iter().any(|row| {
        row.option == "Active data root" && row.value == "/tmp/hyper vector's data"
    }));
    assert!(rows.iter().all(|row| !row.value.contains('{')));
}

#[test]
fn source_follow_config_rows_expose_backend_authority_and_risk() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"source","profile_id":"hypervelocity_source_follow_minrange12_alloc35_shadow_v1","strategy_name":"hypervelocity_source_follow_5m","execution_mode":"shadow","strategy_params":{"leverage":30.0,"target_margin_pct":8.0},"position_policy":{"position_mode":"isolated_one_way","max_positions_per_symbol":1},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","source_revision":"ad15f2bd","execution_timeframe":"5m","primary_timeframe":"5m","context_timeframe":"15m","classified_timeframes":["5m"],"state_1m_role":"not_classified","context_role":"not_classified","context_is_hard_gate":false,"entry_trigger":"confirmed_5m_trend_down_primary_onset","side":"short","minimum_confidence":0.7,"minimum_completed_5m_range_bps":12.0,"maximum_completed_5m_range_bps":100.0,"decision_delay_seconds":300.0,"entry_pulse_seconds":60.0,"session":"24/7","allowed_entry_states":["TREND_DOWN"],"blocked_entry_states":["RANGE","TRANSITION","TREND_UP","BREAKOUT"],"confidence_is_gate":true},"risk":{"margin_fraction":0.35,"notional_fraction":10.5,"max_notional_usd":1700.0},"exits":{"mode":"target_or_maximum_hold_no_fixed_stop","target_margin_pct":8.0,"target_basis":"gross_margin_return_before_fees_and_funding","fixed_stop":"none","maximum_hold_seconds":86400.0,"range_policy":"hold_until_target_or_maximum_hold"},"execution":{"order_type":"limit","time_in_force":"post_only","entry_ttl_seconds":60.0,"target_order_type":"reduce_only_post_only","maximum_hold_exit":"first_fresh_bbo_taker"},"init_cash":15000.0,"equity":15000.0}"#,
    )
    .expect("source telemetry");

    let rows = backend_config_rows(&telemetry);

    assert!(rows.iter().any(|row| {
        row.option == "Profile"
            && row.value == "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"
    }));
    assert!(
        rows.iter()
            .any(|row| row.option == "Leverage" && row.value == "30.0x")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Margin allocation" && row.value == "35.0%")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Maximum hold" && row.value == "24.0h")
    );
    assert!(rows.iter().any(|row| {
        row.option == "Regime engine" && row.value == "pinned_hypertrader_source_follow_v1"
    }));
    assert!(
        rows.iter()
            .any(|row| row.option == "Source side" && row.value == "short")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Minimum confidence" && row.value == "70.0%")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Minimum 5m range" && row.value == "12.0 bps")
    );
    assert!(
        rows.iter().any(|row| {
            row.option == "Maximum-hold exit" && row.value == "first_fresh_bbo_taker"
        })
    );
}

#[test]
fn test_dashboard_uses_backend_margin_costs_and_mark_to_market_pnl() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"risk":{"margin_fraction":0.7},"execution":{"order_type":"limit","time_in_force":"post_only"},"costs":{"maker_fee_rate":0.00015},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"enter_short","run_id":"hv","symbol":"BTC","fill_px":64100.0,"fill_qty":4.36817,"position_qty":-4.36817,"position_avg_px":64100.0,"equity":9958.0,"realized_pnl":-42.0,"unrealized_pnl":0.0,"leverage":40.0,"fee_usd":42.0}
{"feed_ts":"2026-07-25T12:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_DOWN","state_1m":"TREND_DOWN","state_5m":"TREND_DOWN","context_15m":"TREND_DOWN","mark_px":64075.0,"position_qty":-4.36817,"position_avg_px":64100.0,"equity":10067.17,"realized_pnl":-42.0,"unrealized_pnl":109.17}"#,
    )
    .expect("telemetry");
    let snapshots = vec![make_snapshot(
        64075.0,
        64100.0,
        64050.0,
        RegimeState::BearMomentum,
        "2026-07-25T12:01:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw dashboard");
    let buffer = terminal.backend().buffer();
    let rendered = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");

    assert!(rendered.contains("NET PNL:     +67.17 USD"));
    assert!(rendered.contains("MARGIN: $6999.99 (70% Alloc)"));
    assert!(rendered.contains("SHADOW | POST-ONLY MAKER | 1.50bps/side"));
    assert!(rendered.contains("POSITION  #1  ▼ SHORT"));
    assert!(rendered.contains("RUN PNL   +$67.17"));
    assert!(rendered.contains("CLOSED TRADES: 0 | OPEN POSITIONS: 1"));
    assert!(rendered.contains("2026-07-25 08:00:00 EDT"));
    assert!(rendered.contains("Direction"));
    assert!(rendered.contains("Leverage"));
    assert!(rendered.contains("UNREAL +109.17"));
    assert!(rendered.contains("AWAITING TP"));
    assert!(rendered.contains("ENTRY FEE PAID $42.00"));
    assert!(rendered.contains("FUNDING PAID $0.00"), "{rendered}");
    assert!(rendered.contains("EST EXIT FEE"));
    assert!(!rendered.contains("ENTRY READINESS"));
    assert!(!rendered.contains("25% Cap"));
    assert!(!rendered.contains("Taker Drag"));
    assert!(!rendered.contains("+$-"));
}

#[test]
fn flat_position_shows_backend_readiness_and_freshness_state() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T14:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","entry_direction":"long","entry_allowed":true,"entry_retry_state":"blocked_short","entry_cooldown_active":true,"state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","confidence":0.83,"regime_reason":"5m_primary_trend","funding_rate_hourly":0.0000125,"mark_px":101.0,"position_qty":0.0,"equity":10000.0,"realized_pnl":0.0}
{"feed_ts":"2026-07-25T14:01:01Z","action":"submit_entry","run_id":"hv","side":"buy","requested_qty":1.0,"fill_px":101.0,"order_status":"pending"}
{"feed_ts":"2026-07-25T14:01:01Z","action":"entry_execution_observation","run_id":"hv","maker_entry_state":"pending","maker_entry_direction":"long","entry_retry_state":"ready","entry_cooldown_active":false}
{"feed_ts":"2026-07-25T14:01:05Z","action":"book_observation","run_id":"hv","source":"hl_rest_l2","exchange_ts_ms":1784988065000.0,"recv_ts_ms":1784988065050.0,"mid_px":101.25,"spread_bps":4.9382716,"bid_depth_ratio":2.0,"opi":0.3333333,"bids":[{"price":101.0,"size":4.0}],"asks":[{"price":101.5,"size":2.0}]}"#,
    )
    .expect("flat readiness telemetry");
    let snapshots = vec![make_snapshot(
        101.0,
        102.0,
        100.0,
        RegimeState::BullMomentum,
        "2026-07-25T14:01:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.apply_backend_telemetry(telemetry);
    app.book_state.age_ms = 82.0;

    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw flat readiness");
    let buffer = terminal.backend().buffer();
    let rendered = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");

    assert!(rendered.contains("ENTRY READINESS"), "{rendered}");
    assert!(rendered.contains("DIRECTION LONG"), "{rendered}");
    assert!(rendered.contains("REGIME TREND_UP"), "{rendered}");
    assert!(rendered.contains("MAKER PENDING LONG"), "{rendered}");
    assert!(rendered.contains("RETRY READY"), "{rendered}");
    assert!(rendered.contains("COOLDOWN CLEAR"), "{rendered}");
    assert!(rendered.contains("SPREAD 4.9 bps"), "{rendered}");
    assert!(rendered.contains("BOOK BIAS +33.3%"), "{rendered}");
    assert!(rendered.contains("L2 AGE 82 ms"), "{rendered}");
    assert!(rendered.contains("FUNDING +0.00125%/hr"), "{rendered}");
    assert!(rendered.contains("RECENT DECISION"), "{rendered}");
    assert!(rendered.contains("10:01:00 EDT"), "{rendered}");
    assert!(rendered.contains("SCANNING LIVE"), "{rendered}");

    app.book_state.age_ms = 31_000.0;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw stale readiness");
    let stale = (0..terminal.backend().buffer().area.height)
        .map(|y| {
            (0..terminal.backend().buffer().area.width)
                .map(|x| terminal.backend().buffer()[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(stale.contains("TELEMETRY STALE"), "{stale}");

    let narrow_backend = TestBackend::new(100, 40);
    let mut narrow = Terminal::new(narrow_backend).expect("narrow terminal");
    narrow
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw narrow flat readiness");
}

#[test]
fn journal_selection_opens_fee_and_regime_details() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"costs":{"maker_fee_rate":0.00015},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"RANGE","mark_px":100.0,"position_qty":0.0,"realized_pnl":0.0,"equity":10000.0}
{"feed_ts":"2026-07-25T12:01:00Z","action":"enter_long","run_id":"hv","symbol":"BTC","fill_px":100.0,"fill_qty":1.0,"position_qty":1.0,"position_avg_px":100.0,"realized_pnl":-1.5,"equity":9998.5,"fee_usd":1.5}
{"feed_ts":"2026-07-25T13:00:00Z","action":"funding","run_id":"hv","position_qty":1.0,"position_avg_px":100.0,"realized_pnl":-1.7,"unrealized_pnl":5.0,"equity":10003.3,"funding_payment_usd":0.2}
{"feed_ts":"2026-07-25T13:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_UP","mark_px":108.0,"position_qty":1.0,"position_avg_px":100.0,"realized_pnl":-1.7,"unrealized_pnl":8.0,"equity":10006.3}
{"feed_ts":"2026-07-25T13:02:00Z","action":"close","run_id":"hv","symbol":"BTC","fill_px":108.0,"fill_qty":1.0,"position_qty":0.0,"position_avg_px":0.0,"realized_pnl":4.68,"unrealized_pnl":0.0,"equity":10004.68,"fee_usd":1.62,"exit_reason":"take_profit_8pct_margin"}"#,
    )
    .expect("trade telemetry");
    let snapshots = vec![make_snapshot(
        108.0,
        109.0,
        99.0,
        RegimeState::RangeChop,
        "2026-07-25T13:01:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.apply_backend_telemetry(telemetry);
    app.selected_event_index = 3;
    let seed_trade = app.paper_trades[0].clone();
    app.paper_trades = (1..=12)
        .map(|index| {
            let mut trade = seed_trade.clone();
            trade.trade_id = format!("trade-{index:02}");
            trade
        })
        .collect();

    for _ in 0..11 {
        app.select_next_trade();
    }
    assert_eq!(app.selected_trade_index, 11);
    assert_eq!(app.selected_event_index, 3);
    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw selected journal row");
    let journal = (0..terminal.backend().buffer().area.height)
        .map(|y| {
            (0..terminal.backend().buffer().area.width)
                .map(|x| terminal.backend().buffer()[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(journal.contains("trade-01"));

    app.toggle_trade_modal();
    assert!(app.show_trade_detail_modal);
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw trade details");
    let rendered = (0..terminal.backend().buffer().area.height)
        .map(|y| {
            (0..terminal.backend().buffer().area.width)
                .map(|x| terminal.backend().buffer()[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");

    assert!(rendered.contains("TRADE DETAIL INSPECTOR"));
    assert!(rendered.contains("Entry Time"));
    assert!(rendered.contains("2026-07-25 08:01:00 EDT"));
    assert!(rendered.contains("Exit Time"));
    assert!(rendered.contains("2026-07-25 09:02:00 EDT"));
    assert!(
        rendered
            .contains("ENTRY  PRIMARY TREND_UP | 1m TREND_UP | 5m TREND_UP | 15m CONTEXT RANGE")
    );
    assert!(rendered.contains("EXIT   PRIMARY RANGE | 1m RANGE | 5m RANGE | 15m CONTEXT TREND_UP"));
    assert!(rendered.contains("Entry Fee: $1.50"));
    assert!(rendered.contains("Exit Fee: $1.62"));
    assert!(rendered.contains("Funding Paid: $0.20"));
    assert!(rendered.contains("Total Net Costs: $3.32"));
    assert!(rendered.contains("Gross PnL: +$8.00"));
    assert!(rendered.contains("Net PnL: +$4.68"));
}

#[test]
fn dashboard_shows_full_ladder_and_truthful_regime_roles() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T14:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_DOWN","mark_px":100.5,"position_qty":0.0,"equity":10000.0,"realized_pnl":0.0}
{"feed_ts":"2026-07-25T14:01:05Z","action":"book_observation","run_id":"hv","source":"hl_rest_l2","exchange_ts_ms":1784988065000.0,"recv_ts_ms":1784988065050.0,"mid_px":100.5,"spread_bps":9.95,"bid_depth_ratio":1.0,"opi":0.0,"bids":[{"price":100.0,"size":5.0},{"price":99.0,"size":4.0},{"price":98.0,"size":3.0},{"price":97.0,"size":2.0},{"price":96.0,"size":1.0}],"asks":[{"price":101.0,"size":5.0},{"price":102.0,"size":4.0},{"price":103.0,"size":3.0},{"price":104.0,"size":2.0},{"price":105.0,"size":1.0}]}"#,
    )
    .expect("five-level telemetry");
    let snapshots = vec![make_snapshot(
        100.5,
        101.0,
        100.0,
        RegimeState::BullMomentum,
        "2026-07-25T14:01:00Z",
    )];
    let mut app = App::new("BTC".into(), "1m".into(), snapshots, true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw ladder");
    let rendered = (0..terminal.backend().buffer().area.height)
        .map(|y| {
            (0..terminal.backend().buffer().area.width)
                .map(|x| terminal.backend().buffer()[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");

    for price in [105.0, 104.0, 103.0, 102.0, 101.0] {
        assert!(rendered.contains(&format!("ASK  ${price:.2}")));
    }
    for price in [100.0, 99.0, 98.0, 97.0, 96.0] {
        assert!(rendered.contains(&format!("BID  ${price:.2}")));
    }
    assert!(rendered.contains("5m PRIMARY [TREND_UP]"));
    assert!(rendered.contains("15m CONTEXT [TREND_DOWN]"));
    assert!(!rendered.contains("15m BEAR LOCK"));
    assert!(!rendered.contains("HTF Lock: 15m"));
}
