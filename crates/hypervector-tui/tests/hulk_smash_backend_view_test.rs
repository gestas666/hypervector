//! Hulk Smash backend acceptance tests for the read-only TUI.

use hypervector_tui::{
    App, backend_telemetry::parse_backend_telemetry, config_view::backend_config_rows,
};
use ratatui::{Terminal, backend::TestBackend};

const HULK_LEDGER: &str = r#"{"schema_version":1,"sequence":1,"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00Z","execution_mode":"live","effective_mode":"DISARMED","live_armed":false,"execution_authority":"none","profile_id":"hulk_expansion_short_robust_v3_canary_v1","run_id":"hulk-canary","payload":{"symbol":"BTC","strategy_name":"hulk_expansion_short_robust_v3","capital_source":"standalone_canary","portfolio_purpose":"canary_validation","backend_ledger_path":"data/live/hulk_smash/decisions.jsonl","metalabel_mode":"observe","wallet_configured":true,"signing_key_configured":true,"strategy_params":{"leverage":5.0,"minimum_score":7,"pivot_bars":6,"supertrend_period":7,"supertrend_multiplier":3.0,"adx_period":20,"squeeze_period":20,"adx_usable":16.0,"adx_trending":23.0},"position_policy":{"position_mode":"isolated_one_way","max_positions_per_symbol":1},"risk":{"risk_fraction":0.0025,"maximum_portfolio_risk_fraction":0.02,"max_notional_usd":150.0},"regime_policy":{"engine":"hulk_smash_completed_bar_score_v3","classification":"NOT_A_REGIME_CLASSIFIER","signal_timeframe":"30m","execution_timeframe":"next_30m_bar","side":"short_only","completed_bars_only":true},"exits":{"stop_anchor":"prior_6_bar_structural_pivot_clamped","minimum_stop_bps":20.0,"maximum_stop_bps":75.0,"target_r_multiple":3.0,"maximum_hold_bars":48},"execution":{"entry_order_type":"market","protective_stop_order_type":"reduce_only_stop_market","target_order_type":"reduce_only_limit","maximum_hold_exit":"reduce_only_market","maximum_entry_delay_seconds":60,"markout_horizon_ms":5000},"costs":{"maker_fee_rate":0.00015,"taker_fee_rate":0.00045,"funding_source":"venue_account_ledger"},"runtime":{"offline_edge_status":"forward_robustness_survivor_not_live_proven"}}}
{"schema_version":1,"sequence":2,"event_type":"regime_history","observed_at_utc":"2026-08-01T12:00:00Z","execution_mode":"live","run_id":"hulk-canary","payload":{"feed_ts":"2026-08-01T11:30:00Z","reference_price":63850.0,"open":64000.0,"high":64020.0,"low":63820.0,"close":63850.0,"volume":142.0,"primary_regime":"NOT_CLASSIFIED","state_1m":"NOT_CLASSIFIED","state_5m":"NOT_CLASSIFIED","context_15m":"NOT_CLASSIFIED","hulk_candidate":"hulk_rebuilt_expansion_v1","hulk_score":6,"hulk_minimum_score":7,"hulk_trigger":"squeeze_release","hulk_evidence":["squeeze_release","supertrend","ema_trend"],"hulk_stop_anchor":64020.0,"entry_allowed":false,"decision_action":"history_only","regime_reason":"score_below_7"}}
{"schema_version":1,"sequence":3,"event_type":"regime_decision","observed_at_utc":"2026-08-01T12:00:01Z","execution_mode":"live","run_id":"hulk-canary","payload":{"feed_ts":"2026-08-01T12:00:00Z","reference_price":63790.0,"open":63850.0,"high":63880.0,"low":63750.0,"close":63790.0,"volume":180.0,"primary_regime":"NOT_CLASSIFIED","state_1m":"NOT_CLASSIFIED","state_5m":"NOT_CLASSIFIED","context_15m":"NOT_CLASSIFIED","hulk_candidate":"hulk_rebuilt_expansion_v1","hulk_score":8,"hulk_minimum_score":7,"hulk_trigger":"squeeze_release","hulk_evidence":["squeeze_release","supertrend","ema_trend","di_alignment","adx_usable"],"hulk_stop_anchor":63880.0,"entry_direction":"short","short_entry":true,"long_entry":false,"entry_allowed":true,"decision_action":"enter_short","regime_reason":"eligible"}}
{"schema_version":1,"sequence":4,"event_type":"state_transition","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","run_id":"hulk-canary","payload":{"state":"FLAT","entry_oid":null,"protective_stop_oid":null,"target_oid":null,"position_size_signed":0.0}}
{"schema_version":1,"sequence":5,"event_type":"protective_stop_plan","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","run_id":"hulk-canary","payload":{"trigger_price":63880.0,"stop_bps":20.0,"target_price":63520.0,"target_r_multiple":3.0}}
{"schema_version":1,"sequence":6,"event_type":"fee","observed_at_utc":"2026-08-01T12:00:03Z","execution_mode":"live","run_id":"hulk-canary","payload":{"maker_rate":0.00015,"taker_rate":0.00045,"funding_source":"venue_account_ledger"}}"#;

const HULK_LIVE_OPEN_LEDGER: &str = r#"{"schema_version":1,"sequence":1,"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00Z","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"symbol":"BTC","strategy_name":"hulk_expansion_short_robust_v3","strategy_params":{"leverage":5.0},"regime_policy":{"engine":"hulk_smash_completed_bar_score_v3"},"costs":{"funding_source":"venue_account_ledger"}}}
{"schema_version":1,"sequence":2,"event_type":"regime_decision","observed_at_utc":"2026-08-01T12:00:01Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"feed_ts":"2026-08-01T12:00:00Z","reference_price":64000.0,"primary_regime":"NOT_CLASSIFIED","hulk_candidate":"hulk_rebuilt_expansion_v1","hulk_score":8,"hulk_minimum_score":7,"hulk_trigger":"squeeze_release","hulk_evidence":["squeeze_release","adx_usable"],"hulk_stop_anchor":64200.0,"entry_direction":"short","short_entry":true,"entry_allowed":true,"decision_action":"enter_short","regime_reason":"eligible"}}
{"schema_version":1,"sequence":3,"event_type":"fill","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"oid":101,"venue_timestamp_ms":1785585602000,"price":64000.0,"size":0.001,"side":"A","direction":"Open Short","closed_pnl_usd":0.0,"fee_usd":0.0288,"fee_token":"USDC"}}
{"schema_version":1,"sequence":4,"event_type":"position","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"size_signed":-0.001,"entry_price":64000.0,"margin_used_usd":12.8,"position_value_usd":64.0,"unrealized_pnl_usd":0.2,"leverage_type":"isolated","leverage":5}}
{"schema_version":1,"sequence":5,"event_type":"liquidation_price","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"value":75500.0}}
{"schema_version":1,"sequence":6,"event_type":"stop_order","observed_at_utc":"2026-08-01T12:00:03Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"operation":"protective_stop","accepted":true,"oid":201,"status":"accepted","trigger_price":64200.0}}
{"schema_version":1,"sequence":7,"event_type":"target_order","observed_at_utc":"2026-08-01T12:00:03Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"operation":"target","accepted":true,"oid":202,"status":"accepted","limit_price":63400.0}}
{"schema_version":1,"sequence":8,"event_type":"reconciliation","observed_at_utc":"2026-08-01T12:00:04Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"account_value_usd":150.2,"withdrawable_usd":137.2,"open_order_ids":[201,202],"open_orders":[{"oid":201,"size":0.001,"side":"B","reduce_only":true,"is_trigger":true,"trigger_price":64200.0,"limit_price":null,"order_type":"Stop Market"},{"oid":202,"size":0.001,"side":"B","reduce_only":true,"is_trigger":false,"trigger_price":null,"limit_price":63400.0,"order_type":"Limit"}],"fill_ids":[101]}}
{"schema_version":1,"sequence":9,"event_type":"state_transition","observed_at_utc":"2026-08-01T12:00:04Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-live","payload":{"state":"OPEN","entry_oid":101,"stop_oid":201,"target_oid":202,"position_size_signed":-0.001,"opened_at_ms":1785585600000,"entry_price":64000.0,"stop_price":64200.0,"target_price":63400.0}}"#;

const HULK_EXECUTION_METRICS_LEDGER: &str = r#"{"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00Z","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","run_id":"hulk-metrics","payload":{"symbol":"BTC","strategy_name":"hulk_expansion_short_robust_v3","strategy_params":{"leverage":5.0},"risk":{"risk_fraction":0.0025},"exits":{"maximum_hold_bars":48},"execution":{"markout_horizon_ms":5000},"regime_policy":{"engine":"hulk_smash_completed_bar_score_v3"}}}
{"event_type":"regime_decision","observed_at_utc":"2026-08-01T12:00:00.001Z","execution_mode":"live","run_id":"hulk-metrics","payload":{"feed_ts":"2026-08-01T12:00:00Z","reference_price":64000.0,"primary_regime":"NOT_CLASSIFIED","hulk_candidate":"hulk_rebuilt_expansion_v1","hulk_score":8,"hulk_minimum_score":7,"hulk_trigger":"squeeze_release","hulk_evidence":["squeeze_release"],"hulk_stop_anchor":64200.0,"short_entry":true,"entry_allowed":true,"decision_action":"enter_short","regime_reason":"eligible"}}
{"event_type":"order_acknowledgement","observed_at_utc":"2026-08-01T12:00:00.037Z","execution_mode":"live","run_id":"hulk-metrics","payload":{"operation":"entry","accepted":true,"oid":101,"status":"filled","round_trip_latency_ms":37}}
{"event_type":"execution_quality","observed_at_utc":"2026-08-01T12:00:01Z","execution_mode":"live","run_id":"hulk-metrics","payload":{"strategy_id":"hulk_expansion_short_robust_v3","oid":101,"expected_price":64000.0,"fill_price":63936.0,"fill_side":"A","liquidity_side":"taker","slippage_bps":10.0}}
{"event_type":"liquidation_distance","observed_at_utc":"2026-08-01T12:00:02Z","execution_mode":"live","run_id":"hulk-metrics","payload":{"strategy_id":"hulk_expansion_short_robust_v3","side":"short","mark_price":63900.0,"liquidation_price":76680.0,"distance_pct":20.0}}
{"event_type":"fill_markout","observed_at_utc":"2026-08-01T12:00:08.300Z","execution_mode":"live","run_id":"hulk-metrics","payload":{"strategy_id":"hulk_expansion_short_robust_v3","oid":101,"fill_timestamp_ms":1785585601000,"fill_price":63936.0,"fill_side":"A","liquidity_side":"taker","mark_timestamp_ms":1785585608300,"mark_price":63800.0,"horizon_ms":7300,"target_horizon_ms":5000,"horizon_lateness_ms":2300,"recovered_after_restart":true,"markout_bps":21.27002}}"#;

#[test]
fn hulk_projection_preserves_score_evidence_and_execution_levels() {
    let telemetry = parse_backend_telemetry(HULK_LEDGER).expect("Hulk telemetry");

    assert!(telemetry.is_hulk_smash());
    assert_eq!(telemetry.hulk_smash.score, Some(8));
    assert_eq!(telemetry.hulk_smash.minimum_score, Some(7));
    assert_eq!(
        telemetry.hulk_smash.trigger.as_deref(),
        Some("squeeze_release")
    );
    assert_eq!(telemetry.hulk_smash.evidence.len(), 5);
    assert_eq!(telemetry.hulk_smash.stop_anchor, Some(63_880.0));
    assert_eq!(telemetry.hulk_smash.planned_stop_price, Some(63_880.0));
    assert_eq!(telemetry.hulk_smash.planned_target_price, Some(63_520.0));
    assert_eq!(telemetry.live_armed, Some(false));
    assert_eq!(
        telemetry
            .costs
            .get("funding_source")
            .and_then(|value| value.as_str()),
        Some("venue_account_ledger")
    );
}

#[test]
fn hulk_dashboard_and_signal_screen_do_not_claim_regime_classification() {
    let telemetry = parse_backend_telemetry(HULK_LEDGER).expect("Hulk telemetry");
    let mut app = App::new("BTC".into(), "30m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Hulk dashboard");
    let dashboard = rendered(&terminal);
    assert!(
        dashboard.contains("HULK EXPANSION SHORT ROBUST V3 5x"),
        "{dashboard}"
    );
    assert!(dashboard.contains("30m SCORE 8/7"), "{dashboard}");
    assert!(dashboard.contains("SHORT ONLY"), "{dashboard}");
    assert!(dashboard.contains("SQUEEZE RELEASE"), "{dashboard}");
    assert!(dashboard.contains("REGIME NOT CLASSIFIED"), "{dashboard}");
    assert!(!dashboard.contains("5m PRIMARY"), "{dashboard}");

    app.active_tab = 1;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Hulk signal screen");
    let signal = rendered(&terminal);
    assert!(signal.contains("[2] SIGNAL ENGINE"), "{signal}");
    assert!(signal.contains("HULK SMASH 30m SIGNAL ENGINE"), "{signal}");
    assert!(signal.contains("SCORE 8 / 7"), "{signal}");
    assert!(signal.contains("COMPLETED BARS ONLY"), "{signal}");
    assert!(signal.contains("MAX ENTRY AGE 60s"), "{signal}");
    assert!(signal.contains("NO REGIME CLASSIFICATION"), "{signal}");
    assert!(signal.contains("ADX_USABLE"), "{signal}");
    assert!(!signal.contains("FULL 3-TF ALIGNMENT"), "{signal}");
}

#[test]
fn hulk_live_open_projection_uses_exact_backend_position_and_bracket() {
    let telemetry = parse_backend_telemetry(HULK_LIVE_OPEN_LEDGER).expect("live Hulk telemetry");

    assert_eq!(telemetry.live_armed, Some(true));
    assert_eq!(telemetry.live_state.as_deref(), Some("OPEN"));
    assert_eq!(telemetry.active_position.direction, "SHORT");
    assert_eq!(telemetry.active_position.size_btc, 0.001);
    assert_eq!(telemetry.active_position.entry_price, 64_000.0);
    assert_eq!(telemetry.active_position.liquidation_price, Some(75_500.0));
    assert_eq!(telemetry.protective_stop_oid, Some(201));
    assert_eq!(telemetry.protective_stop_price, Some(64_200.0));
    assert_eq!(telemetry.target_order_oid, Some(202));
    assert_eq!(telemetry.target_order_price, Some(63_400.0));
}

#[test]
fn hulk_execution_metrics_are_projected_and_rendered_without_inference() {
    let telemetry = parse_backend_telemetry(HULK_EXECUTION_METRICS_LEDGER).expect("Hulk metrics");

    assert_eq!(telemetry.hulk_smash.latest_ack_latency_ms, Some(37));
    assert_eq!(telemetry.hulk_smash.latest_slippage_bps, Some(10.0));
    assert_eq!(telemetry.hulk_smash.latest_markout_bps, Some(21.27002));
    assert_eq!(telemetry.hulk_smash.latest_markout_horizon_ms, Some(7_300));
    assert_eq!(telemetry.hulk_smash.latest_markout_target_ms, Some(5_000));
    assert_eq!(telemetry.hulk_smash.latest_markout_lateness_ms, Some(2_300));
    assert_eq!(
        telemetry.hulk_smash.latest_markout_recovered_after_restart,
        Some(true)
    );
    assert_eq!(telemetry.hulk_smash.liquidation_distance_pct, Some(20.0));
    assert_eq!(
        telemetry.hulk_smash.latest_liquidity_side.as_deref(),
        Some("taker")
    );

    let mut app = App::new("BTC".into(), "30m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 1;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Hulk metrics");
    let screen = rendered(&terminal);
    assert!(screen.contains("ACK 37ms"), "{screen}");
    assert!(screen.contains("SLIPPAGE +10.00 bps"), "{screen}");
    assert!(
        screen.contains("7.3s MARKOUT +21.27 bps [TARGET 5s · RESTART +2.3s]"),
        "{screen}"
    );
    assert!(screen.contains("LIQ DIST 20.00%"), "{screen}");
}

#[test]
fn hulk_chart_and_config_report_the_frozen_candidate_contract() {
    let telemetry = parse_backend_telemetry(HULK_LEDGER).expect("Hulk telemetry");
    let rows = backend_config_rows(&telemetry);
    assert!(
        rows.iter()
            .any(|row| row.option == "Signal score" && row.value == "7")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Structural pivot" && row.value == "6 bars")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Stop clamp" && row.value == "20.0-75.0 bps")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Profit target" && row.value == "3.0R")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Maximum entry age" && row.value == "60 seconds")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Markout horizon" && row.value == "5000 ms")
    );
    assert!(rows.iter().any(|row| row.option == "Offline status"
        && row.value == "forward_robustness_survivor_not_live_proven"));

    let mut app = App::new("BTC".into(), "30m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 2;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Hulk chart");
    let chart = rendered(&terminal);
    assert!(chart.contains("HULK SMASH · BACKEND ONLY"), "{chart}");
    assert!(chart.contains("STOP $63880.00"), "{chart}");
    assert!(chart.contains("TARGET $63520.00"), "{chart}");
    assert!(chart.contains("3.0R"), "{chart}");
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
