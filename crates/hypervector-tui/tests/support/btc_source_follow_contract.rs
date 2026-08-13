const BTC_SOURCE_LEDGER: &str = r#"{"schema_version":1,"sequence":1,"event_type":"configuration_identity","observed_at_utc":"2026-07-31T16:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"symbol":"BTC","strategy_name":"hypervelocity_source_follow_5m","capital_source":"standalone_canary","portfolio_purpose":"canary_validation","backend_ledger_path":"data/live/hypervelocity_source_follow/decisions.jsonl","metalabel_mode":"observe","metalabel_policy":{"observation_type":"annotation_collection","inference_active":false,"bundle_id":null,"probabilities_emitted":false,"may_filter":false,"may_scale":false,"execution_authority":"none"},"wallet_configured":true,"signing_key_configured":true,"strategy_params":{"leverage":30.0,"target_margin_pct":8.0},"position_policy":{"position_mode":"isolated_one_way","max_positions_per_symbol":1},"risk":{"margin_fraction":0.35,"notional_fraction":10.5,"max_notional_usd":1700.0},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","source_revision":"ad15f2bd","execution_timeframe":"5m","primary_timeframe":"5m","context_timeframe":"15m","classified_timeframes":["5m"],"state_1m_role":"not_classified","context_role":"not_classified","context_is_hard_gate":false,"entry_trigger":"confirmed_5m_trend_down_primary_onset","side":"short","minimum_confidence":0.7,"minimum_completed_5m_range_bps":12.0,"maximum_completed_5m_range_bps":100.0,"decision_delay_seconds":300.0,"entry_pulse_seconds":60.0,"session":"24/7","allowed_entry_states":["TREND_DOWN"],"blocked_entry_states":["RANGE","TRANSITION","TREND_UP","BREAKOUT"],"confidence_is_gate":true},"observer_policies":{"execution_authority":"none","side":"long","recipes":["bk_up_asia_conf06","fade_td_eu","bk_up_24h_challenger","trend_up_24h_challenger","trend_down_24h_direction_challenger"]},"exits":{"mode":"target_or_maximum_hold_no_fixed_stop","target_margin_pct":8.0,"target_price_fraction":0.0026666666666666666,"target_basis":"gross_margin_return_before_fees_and_funding","fixed_stop":"none","maximum_hold_seconds":86400.0,"range_policy":"hold_until_target_or_maximum_hold"},"execution":{"order_type":"limit","time_in_force":"post_only","entry_ttl_seconds":60.0,"target_order_type":"reduce_only_post_only","maximum_hold_exit":"first_fresh_bbo_taker"}}}
{"schema_version":1,"sequence":2,"event_type":"regime_decision","observed_at_utc":"2026-07-31T16:05:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"reference_price":64000.0,"primary_regime":"TREND_DOWN","state_1m":"NOT_CLASSIFIED","state_5m":"TREND_DOWN","context_15m":"NOT_CLASSIFIED","confidence":0.82,"regime_score_source":"pinned_hypertrader_classifier_confidence","primary_onset":true,"source_event":true,"entry_direction":"short","short_entry":true,"long_entry":false,"entry_allowed":true,"regime_admitted":true,"source_long_observer":{"authority":"observe_only","recipe_id":"fade_td_eu","side":"long","maximum_hold_seconds":86400.0},"decision_action":"enter_short","regime_reason":"source_follow_entry_pulse","source_follow_signal_range_bps":18.0,"entry_pulse_expires_at_utc":"2026-07-31T16:06:00+00:00"}}
{"schema_version":1,"sequence":3,"event_type":"book_observation","observed_at_utc":"2026-07-31T16:05:01+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"source":"hyperliquid_mainnet_l2_rest","exchange_ts_ms":1785513901000,"recv_ts_ms":1785513901010,"mid_px":64000.0,"spread_bps":0.2,"bid_depth_ratio":1.1,"opi":0.0476,"bids":[{"price":63999.0,"size":1.0}],"asks":[{"price":64001.0,"size":0.9}]}}
{"schema_version":1,"sequence":4,"event_type":"fee","observed_at_utc":"2026-07-31T16:05:01+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"maker_rate":0.00015,"taker_rate":0.00045}}
{"schema_version":1,"sequence":5,"event_type":"fill","observed_at_utc":"2026-07-31T16:05:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"oid":101,"price":64001.0,"size":0.025,"side":"A","direction":"Open Short","closed_pnl_usd":0.0,"crossed":false,"fee_usd":0.24}}
{"schema_version":1,"sequence":6,"event_type":"position","observed_at_utc":"2026-07-31T16:05:03+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"size_signed":-0.025,"entry_price":64001.0,"unrealized_pnl_usd":0.025,"leverage_type":"isolated","leverage":30.0}}
{"schema_version":1,"sequence":7,"event_type":"liquidation_price","observed_at_utc":"2026-07-31T16:05:03+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"value":66010.0}}
{"schema_version":1,"sequence":8,"event_type":"reconciliation","observed_at_utc":"2026-07-31T16:05:04+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"account_value_usd":153.61,"withdrawable_usd":100.27,"open_orders":[{"oid":202,"size":0.025,"side":"B","reduce_only":true,"is_trigger":false,"limit_price":63830.33,"order_type":"Limit"}]}}
{"schema_version":1,"sequence":9,"event_type":"state_transition","observed_at_utc":"2026-07-31T16:05:04+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_minrange12_alloc35_live_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"btc-source-live","payload":{"state":"OPEN_TARGET_RESTING","entry_oid":101,"target_oid":202,"position_size_signed":-0.025,"opened_at_ms":1785513902000}}"#;

#[test]
fn backend_timeframe_roles_override_ambiguous_cli_label() {
    let telemetry = parse_backend_telemetry(BTC_SOURCE_LEDGER).expect("BTC source telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw BTC source dashboard");

    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("DECISION: 5m"));
    assert!(dashboard.contains("ENTRY WINDOW: 60s"));
    assert!(!dashboard.contains("EXEC: 1m"));
    assert!(dashboard.contains("5m SOURCE [TREND_DOWN]"));
    assert!(dashboard.contains("SHORT EXEC"));
    assert!(dashboard.contains("LONG OBS FADE_TD_EU"));
    assert!(dashboard.contains("1m/15m NOT CLASSIFIED"));
    assert!(dashboard.contains("ENTRY/TARGET MAKER"));
    assert!(dashboard.contains("MAX-HOLD TAKER"));
    assert!(dashboard.contains("HYPERVELOCITY SOURCE FOLLOW 5M 30x"));
    assert!(dashboard.contains("TARGET $63830.33 OID 202 RESTING"));
    assert!(dashboard.contains("LIQ PRICE  $66010.00"));
    assert!(dashboard.contains("LIVE EXECUTION JOURNAL"));
    assert!(!dashboard.contains("LIVE PAPER JOURNAL"));
}

#[test]
fn regime_screen_marks_only_five_minute_source_as_classified() {
    let telemetry = parse_backend_telemetry(BTC_SOURCE_LEDGER).expect("BTC source telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 1;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw BTC source regime screen");

    let regime = rendered(&terminal);
    assert!(regime.contains("5m SOURCE ENTRY AUTHORITY"));
    assert!(regime.contains("1m [NOT_CLASSIFIED] UNUSED"));
    assert!(regime.contains("15m [NOT_CLASSIFIED] UNUSED"));
    assert!(regime.contains("SINGLE-TIMEFRAME SOURCE SIGNAL"));
    assert!(regime.contains("SHORT EXECUTION | SOURCE LONGS OBSERVE ONLY"));
    assert!(regime.contains("SOURCE CONFIDENCE 82.0%"));
    assert!(!regime.contains("FULL 3-TF ALIGNMENT"));
    assert!(!regime.contains("PARTIAL ALIGNMENT"));
}

#[test]
fn regime_screen_exposes_source_raw_state_and_hysteresis_diagnostics() {
    let ledger = r#"{"run_id":"diagnostics","action":"session_start","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","minimum_confidence":0.7}}
{"run_id":"diagnostics","action":"regime_observation","feed_ts":"2026-07-31T16:05:00Z","primary_regime":"RANGE","state_1m":"NOT_CLASSIFIED","state_5m":"RANGE","context_15m":"NOT_CLASSIFIED","confidence":0.55,"mark_px":64000.0,"regime_diagnostics":{"authority":"telemetry_only","raw_primary":"TREND_DOWN","raw_secondary":null,"raw_confidence":0.8,"confirmed_primary":"RANGE","state_filtered":true,"adx":12.5,"adx_percentile_rank":0.31,"adx_range_percentile_threshold":0.4,"adx_weak_percentile_threshold":0.5,"ema_alignment":"bearish","rsi":48.0,"volume_ratio":0.8,"range_break_up":false,"range_break_down":false}}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("source diagnostics");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 1;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw source regime diagnostics");

    let regime = rendered(&terminal);
    assert!(
        regime.contains("CONFIRMED [RANGE] | RAW [TREND_DOWN]"),
        "{regime}"
    );
    assert!(regime.contains("HYSTERESIS FILTERED"), "{regime}");
    assert!(regime.contains("ADX PCTL 31.0% | RANGE <40.0%"), "{regime}");
    assert!(
        regime.contains("EMA bearish | BREAK UP NO DOWN NO"),
        "{regime}"
    );
}

#[test]
fn source_diagnostics_reject_a_confirmed_state_mismatch() {
    let ledger = r#"{"run_id":"diagnostics","action":"regime_observation","feed_ts":"2026-07-31T16:05:00Z","primary_regime":"RANGE","regime_diagnostics":{"authority":"telemetry_only","raw_primary":"TREND_DOWN","raw_secondary":null,"raw_confidence":0.8,"confirmed_primary":"TREND_UP","state_filtered":true,"adx":12.5,"adx_percentile_rank":0.31,"adx_range_percentile_threshold":0.4,"adx_weak_percentile_threshold":0.5,"ema_alignment":"bearish","rsi":48.0,"volume_ratio":0.8,"range_break_up":false,"range_break_down":false}}"#;

    let error = parse_backend_telemetry(ledger).expect_err("mismatch must fail closed");

    assert!(
        error
            .to_string()
            .contains("diagnostic confirmed regime TREND_UP differs from RANGE"),
        "{error}"
    );
}

#[test]
fn chart_screen_reports_source_follow_contract_without_canonical_tactical_fields() {
    let telemetry = parse_backend_telemetry(BTC_SOURCE_LEDGER).expect("BTC source telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 2;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw BTC source chart");

    let chart = rendered(&terminal);
    assert!(chart.contains("BTC SOURCE-FOLLOW · BACKEND ONLY"));
    assert!(chart.contains("5m SOURCE TREND_DOWN"));
    assert!(chart.contains("CONF 82.0% >= 70.0%"));
    assert!(chart.contains("RANGE 18.0 bps IN [12.0, 100.0]"));
    assert!(chart.contains("TARGET 8.0% GROSS"));
    assert!(chart.contains("NO FIXED STOP"));
    assert!(chart.contains("MAX HOLD 24.0h"));
    assert!(!chart.contains("BBWP"));
    assert!(!chart.contains("RSI X"));
}

#[test]
fn chart_screen_renders_backend_history_ohlcv_without_execution_authority() {
    let ledger = r#"{"run_id":"chart","event_type":"configuration_identity","observed_at_utc":"2026-07-31T16:10:00Z","execution_mode":"live","payload":{"symbol":"BTC","strategy_name":"hypervelocity_source_follow_5m","strategy_params":{"leverage":30.0},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","side":"bidirectional"}}}
{"run_id":"chart","event_type":"regime_history","observed_at_utc":"2026-07-31T16:10:00Z","execution_mode":"live","payload":{"feed_ts":"2026-07-31T16:00:00Z","primary_regime":"RANGE","state_5m":"RANGE","confidence":0.70,"reference_price":64000.0,"open":63950.0,"high":64020.0,"low":63900.0,"volume":123.45,"entry_allowed":false,"decision_action":"history_only"}}
{"run_id":"chart","event_type":"regime_history","observed_at_utc":"2026-07-31T16:10:00Z","execution_mode":"live","payload":{"feed_ts":"2026-07-31T16:05:00Z","primary_regime":"TREND_UP","state_5m":"TREND_UP","confidence":0.82,"reference_price":64050.0,"open":64000.0,"high":64080.0,"low":63980.0,"volume":150.0,"entry_allowed":false,"decision_action":"history_only"}}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("source chart history");

    assert_eq!(telemetry.regime_snapshots.len(), 2);
    assert_eq!(telemetry.latest_regime.as_deref(), Some("TREND_UP"));
    assert_eq!(telemetry.entry_allowed, Some(false));
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 2;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw source chart history");

    let chart = rendered(&terminal);
    assert!(!chart.contains("OPEN DATA UNAVAILABLE"), "{chart}");
    assert!(!chart.contains("$    0.01"), "{chart}");
    assert!(chart.contains("│  150.00"), "{chart}");
}

#[test]
fn config_screen_reports_selected_source_follow_contract() {
    let telemetry = parse_backend_telemetry(BTC_SOURCE_LEDGER).expect("BTC source telemetry");
    let rows = backend_config_rows(&telemetry);

    assert!(
        rows.iter()
            .any(|row| row.option == "Primary regime timeframe" && row.value == "5m")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Decision timeframe" && row.value == "5m")
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "1m classification" && row.value == "not_classified" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "15m classification" && row.value == "not_classified" })
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Context timeframe" && row.value == "15m")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Margin allocation" && row.value == "35.0%")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Leverage" && row.value == "30.0x")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Minimum 5m range" && row.value == "12.0 bps")
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Protective stop" && row.value == "none" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Target basis" && row.value == "gross_margin_return_before_fees_and_funding"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Long observer authority" && row.value == "none" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Metalabel observation" && row.value == "annotation_collection"
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Metalabel inference" && row.value == "inactive" })
    );
    assert!(rows.iter().any(|row| {
        row.option == "Long observer recipes"
            && row.value
                == "bk_up_asia_conf06, fade_td_eu, bk_up_24h_challenger, trend_up_24h_challenger, trend_down_24h_direction_challenger"
    }));
}

#[test]
fn source_follow_readiness_follows_backend_lifecycle_not_stale_decision() {
    let prefix = r#"{"run_id":"source-state","action":"session_start","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}
{"run_id":"source-state","action":"regime_observation","primary_regime":"TREND_DOWN","state_1m":"NOT_CLASSIFIED","state_5m":"TREND_DOWN","context_15m":"NOT_CLASSIFIED","entry_allowed":true,"entry_direction":"short"}"#;
    let pending = format!(
        "{prefix}\n{}",
        r#"{"run_id":"source-state","action":"state_transition","state":"ENTRY_PENDING"}"#
    );
    let expired = format!(
        "{pending}\n{}",
        r#"{"run_id":"source-state","action":"state_transition","state":"FLAT"}"#
    );

    let pending_state = parse_backend_telemetry(&pending).expect("pending source state");
    assert_eq!(pending_state.entry_allowed, Some(true));
    assert_eq!(
        pending_state.pending_entry_direction.as_deref(),
        Some("short")
    );

    let expired_state = parse_backend_telemetry(&expired).expect("expired source state");
    assert_eq!(expired_state.entry_allowed, Some(false));
    assert_eq!(expired_state.pending_entry_direction, None);
}

#[test]
fn flat_source_follow_labels_classifier_confidence_without_structure_alias() {
    let ledger = r#"{"run_id":"source-flat","action":"session_start","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}
{"run_id":"source-flat","action":"regime_observation","feed_ts":"2026-07-31T16:05:00Z","primary_regime":"TREND_DOWN","state_1m":"NOT_CLASSIFIED","state_5m":"TREND_DOWN","context_15m":"NOT_CLASSIFIED","confidence":0.82,"regime_score_source":"pinned_hypertrader_classifier_confidence","mark_px":64000.0,"position_qty":0.0}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("flat source telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw flat BTC source dashboard");

    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("SOURCE CONF 82.0%"), "{dashboard}");
    assert!(!dashboard.contains("STRUCTURE 82.0%"), "{dashboard}");
}

#[test]
fn live_source_journal_treats_closed_pnl_as_per_fill_not_cumulative() {
    let ledger = r#"{"run_id":"pnl","event_type":"configuration_identity","observed_at_utc":"2026-07-31T12:00:00Z","execution_mode":"live","payload":{"symbol":"BTC","strategy_name":"hypervelocity_source_follow_5m","strategy_params":{"leverage":30.0},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}}
{"run_id":"pnl","event_type":"regime_decision","observed_at_utc":"2026-07-31T12:00:00Z","execution_mode":"live","payload":{"primary_regime":"TREND_DOWN","state_5m":"TREND_DOWN"}}
{"run_id":"pnl","event_type":"fill","observed_at_utc":"2026-07-31T12:01:00Z","execution_mode":"live","payload":{"price":100.0,"size":1.0,"direction":"Open Short","closed_pnl_usd":0.0,"fee_usd":0.01}}
{"run_id":"pnl","event_type":"fill","observed_at_utc":"2026-07-31T12:02:00Z","execution_mode":"live","payload":{"price":99.0,"size":1.0,"direction":"Close Short","closed_pnl_usd":1.0,"fee_usd":0.01}}
{"run_id":"pnl","event_type":"fill","observed_at_utc":"2026-07-31T12:03:00Z","execution_mode":"live","payload":{"price":100.0,"size":1.0,"direction":"Open Short","closed_pnl_usd":0.0,"fee_usd":0.01}}
{"run_id":"pnl","event_type":"fill","observed_at_utc":"2026-07-31T12:04:00Z","execution_mode":"live","payload":{"price":98.0,"size":1.0,"direction":"Close Short","closed_pnl_usd":2.0,"fee_usd":0.01}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("two live source trades");

    assert_eq!(telemetry.trades.len(), 2);
    assert_eq!(telemetry.trades[0].pnl_usd, 1.0);
    assert_eq!(telemetry.trades[1].pnl_usd, 2.0);
}

#[test]
fn live_source_journal_waits_for_flat_and_aggregates_partial_target_fills() {
    let prefix = r#"{"run_id":"partial","event_type":"configuration_identity","observed_at_utc":"2026-07-31T12:00:00Z","execution_mode":"live","payload":{"symbol":"BTC","strategy_name":"hypervelocity_source_follow_5m","strategy_params":{"leverage":30.0},"regime_policy":{"engine":"pinned_hypertrader_source_follow_v1"}}}
{"run_id":"partial","event_type":"regime_decision","observed_at_utc":"2026-07-31T12:00:00Z","execution_mode":"live","payload":{"primary_regime":"TREND_DOWN","state_5m":"TREND_DOWN"}}
{"run_id":"partial","event_type":"fill","observed_at_utc":"2026-07-31T12:01:00Z","execution_mode":"live","payload":{"price":100.0,"size":1.0,"direction":"Open Short","closed_pnl_usd":0.0,"fee_usd":0.01}}
{"run_id":"partial","event_type":"position","observed_at_utc":"2026-07-31T12:01:01Z","execution_mode":"live","payload":{"size_signed":-1.0,"entry_price":100.0}}
{"run_id":"partial","event_type":"position","observed_at_utc":"2026-07-31T12:02:00Z","execution_mode":"live","payload":{"size_signed":-0.6,"entry_price":100.0}}
{"run_id":"partial","event_type":"fill","observed_at_utc":"2026-07-31T12:02:01Z","execution_mode":"live","payload":{"price":99.0,"size":0.4,"direction":"Close Short","closed_pnl_usd":0.4,"fee_usd":0.004}}"#;
    let completed = format!(
        "{prefix}\n{}\n{}\n{}",
        r#"{"run_id":"partial","event_type":"position","observed_at_utc":"2026-07-31T12:03:00Z","execution_mode":"live","payload":{"size_signed":0.0,"entry_price":null}}"#,
        r#"{"run_id":"partial","event_type":"fill","observed_at_utc":"2026-07-31T12:03:01Z","execution_mode":"live","payload":{"price":98.0,"size":0.6,"direction":"Close Short","closed_pnl_usd":1.2,"fee_usd":0.006}}"#,
        r#"{"run_id":"partial","event_type":"close","observed_at_utc":"2026-07-31T12:03:02Z","execution_mode":"live","payload":{"reason":"target","oid":202,"verified_flat":true}}"#
    );

    let partial = parse_backend_telemetry(prefix).expect("partial target state");
    assert!(partial.trades.is_empty());
    assert_eq!(partial.active_position.size_btc, 0.6);

    let flat = parse_backend_telemetry(&completed).expect("completed target state");
    assert_eq!(flat.trades.len(), 1);
    assert_eq!(flat.trades[0].size_btc, 1.0);
    assert!((flat.trades[0].exit_price - 98.4).abs() < 1e-9);
    assert!((flat.trades[0].pnl_usd - 1.6).abs() < 1e-9);
    assert!((flat.trades[0].exit_fee_usd - 0.01).abs() < 1e-9);
    assert_eq!(flat.trades[0].exit_reason, "target");
}

#[test]
fn bidirectional_source_contract_is_visible_as_two_sided_execution() {
    let ledger = r#"{"run_id":"bidir","event_type":"configuration_identity","observed_at_utc":"2026-07-31T16:00:00Z","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1","payload":{"symbol":"BTC","strategy_name":"hypervelocity_source_follow_5m","regime_policy":{"engine":"pinned_hypertrader_source_follow_v1","side":"bidirectional","primary_timeframe":"5m","context_timeframe":"15m","minimum_confidence":0.7}}}
{"run_id":"bidir","event_type":"regime_decision","observed_at_utc":"2026-07-31T16:05:00Z","execution_mode":"live","payload":{"primary_regime":"TREND_UP","state_1m":"NOT_CLASSIFIED","state_5m":"TREND_UP","context_15m":"NOT_CLASSIFIED","confidence":0.82,"entry_direction":"long","long_entry":true,"short_entry":false,"entry_allowed":true,"decision_action":"enter_long"}}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("bidirectional telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw bidirectional dashboard");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("LONG + SHORT EXEC"), "{dashboard}");
    assert!(dashboard.contains("ACTION ENTER LONG"), "{dashboard}");

    app.active_tab = 1;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw bidirectional regime screen");
    let regime = rendered(&terminal);
    assert!(regime.contains("BIDIRECTIONAL EXECUTION"), "{regime}");
    assert!(!regime.contains("SOURCE LONGS OBSERVE ONLY"), "{regime}");
}

#[test]
fn measured_source_dashboard_reports_exact_risk_and_evidence_limits() {
    let telemetry = parse_backend_telemetry(MEASURED_LEDGER).expect("measured telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw measured dashboard");
    let dashboard = rendered(&terminal);
    assert!(
        dashboard.contains("HYPERVELOCITY SOURCE FOLLOW 5M 5x"),
        "{dashboard}"
    );
    assert!(dashboard.contains("RISK 10.0% MARGIN"), "{dashboard}");
    assert!(dashboard.contains("0.50x EQUITY NOTIONAL"), "{dashboard}");
    assert!(
        dashboard.contains("TARGET 1.33% GROSS MARGIN / 26.67 bps PRICE"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("DEVELOPMENT CANDIDATE NOT LIVE PROVEN"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("EXECUTION ECONOMICS INCONCLUSIVE"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("2 ACTIVE BOOK-GAP WINDOWS"),
        "{dashboard}"
    );
    assert!(!dashboard.contains("CAP $0"), "{dashboard}");
}

#[test]
fn measured_source_dashboard_keeps_critical_contract_at_compact_floor() {
    let telemetry = parse_backend_telemetry(MEASURED_LEDGER).expect("measured telemetry");
    let mut app = App::new("BTC".into(), "5m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(120, 36);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw compact measured dashboard");
    let dashboard = rendered(&terminal);
    assert!(
        dashboard.contains("RISK 10.0% x 5.00x = 0.50x NOTIONAL"),
        "{dashboard}"
    );
    assert!(dashboard.contains("TP 1.33% / 26.67bps"), "{dashboard}");
    assert!(
        dashboard.contains("DEV ONLY | EXEC INCONCLUSIVE | BOOK GAPS 2"),
        "{dashboard}"
    );
    assert!(dashboard.contains("EXEC SHADOW"), "{dashboard}");
    assert!(dashboard.contains("FEED LIVE"), "{dashboard}");
    assert!(dashboard.contains("CONNECTED"), "{dashboard}");
    assert!(!dashboard.contains("CAP $0"), "{dashboard}");
}
