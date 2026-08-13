//! Apex MM backend-ledger acceptance tests for the read-only TUI.

use hypervector_tui::{
    App,
    backend_telemetry::{BackendConnectionState, parse_backend_telemetry},
    config_view::backend_config_rows,
};
use ratatui::{Terminal, backend::TestBackend};

#[test]
fn projects_mm_quotes_inventory_oids_and_markout_without_regime_invention() {
    let ledger = r#"{"schema_version":1,"sequence":1,"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"symbol":"BTC","strategy_name":"apex_regime_mm_v2","capital_source":"standalone_canary","portfolio_purpose":"execution_friction_measurement","backend_ledger_path":"data/live/apex_regime_mm/decisions.jsonl","metalabel_mode":"disabled","strategy_params":{"leverage":3.0},"regime_policy":{"engine":"not_used_for_market_maker_entries","classification":"NOT_CLASSIFIED"}}}
{"schema_version":1,"sequence":2,"event_type":"reconciliation","observed_at_utc":"2026-08-01T12:00:00.1+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"account_value_usd":150.0,"withdrawable_usd":145.0,"open_order_ids":[101,102],"open_orders":[],"fill_ids":[]}}
{"schema_version":1,"sequence":3,"event_type":"position","observed_at_utc":"2026-08-01T12:00:00.2+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"size_signed":0.0002,"entry_price":65000.0,"margin_used_usd":4.333,"position_value_usd":13.0,"unrealized_pnl_usd":0.05,"leverage_type":"isolated","leverage":3}}
{"schema_version":1,"sequence":4,"event_type":"book_observation","observed_at_utc":"2026-08-01T12:00:00.3+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"source":"hyperliquid_mainnet_l2_rest","exchange_ts_ms":1785585600300,"recv_ts_ms":1785585600310,"mid_px":65000.5,"spread_bps":0.1538,"bid_depth_ratio":1.5,"opi":0.2,"bids":[{"price":65000.0,"size":1.0}],"asks":[{"price":65001.0,"size":0.5}]}}
{"schema_version":1,"sequence":5,"event_type":"theoretical_quote","observed_at_utc":"2026-08-01T12:00:00.4+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","active":true,"reason":"active","fair_value":65000.7,"bid_price":64987.0,"ask_price":65014.0,"bid_size":0.00015,"ask_size":0.00023,"full_spread_bps":4.15,"inventory_utilization":0.433,"inventory_notional_usd":13.0}}
{"schema_version":1,"sequence":6,"event_type":"state_transition","observed_at_utc":"2026-08-01T12:00:00.5+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","state":"INVENTORY","bid_oid":101,"ask_oid":102,"position_size_signed":0.0002,"quote_started_at_ms":1785585600500,"last_fault":null}}
{"schema_version":1,"sequence":7,"event_type":"fill_markout","observed_at_utc":"2026-08-01T12:00:01.5+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","oid":101,"fill_timestamp_ms":1785585600500,"fill_price":64987.0,"fill_size":0.00015,"fill_side":"B","liquidity_side":"maker","mark_timestamp_ms":1785585601500,"mark_price":64990.0,"horizon_ms":1000,"markout_bps":0.46163}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("Apex MM telemetry");

    assert_eq!(
        telemetry.strategy_name.as_deref(),
        Some("apex_regime_mm_v2")
    );
    assert_eq!(telemetry.live_state.as_deref(), Some("INVENTORY"));
    assert_eq!(telemetry.apex_mm.bid_oid, Some(101));
    assert_eq!(telemetry.apex_mm.ask_oid, Some(102));
    assert_eq!(telemetry.apex_mm.bid_price, Some(64987.0));
    assert_eq!(telemetry.apex_mm.ask_price, Some(65014.0));
    assert_eq!(telemetry.apex_mm.inventory_notional_usd, Some(13.0));
    assert_eq!(telemetry.apex_mm.latest_markout_bps, Some(0.46163));
    assert_eq!(telemetry.apex_mm.markout_horizon_ms, Some(1000));
    assert_eq!(telemetry.regime_snapshots.len(), 1);
    assert_eq!(
        telemetry.regime_snapshots[0].regime_reason,
        "backend_book_display_only_not_classified"
    );
    assert_eq!(telemetry.regime_snapshots[0].trend_5m, "NOT_CLASSIFIED");
    assert_eq!(telemetry.latest_regime, None);

    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Apex MM dashboard");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("BTC MARKET MAKER 3x"), "{dashboard}");
    assert!(dashboard.contains("REGIME NOT CLASSIFIED"), "{dashboard}");
    assert!(!dashboard.contains("3x █  UNKNOWN"), "{dashboard}");
    assert!(
        dashboard.contains("BACKEND CONNECTED  |  ENGINE INVENTORY"),
        "{dashboard}"
    );
    assert!(dashboard.contains("BUY #101 $64987"), "{dashboard}");
    assert!(dashboard.contains("SELL #102 $65014"), "{dashboard}");
    assert!(dashboard.contains("INV $13.00"), "{dashboard}");
    assert!(dashboard.contains("1s +0.46bps"), "{dashboard}");
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

fn strategy_view_ledger() -> &'static str {
    r#"{"schema_version":1,"sequence":1,"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"symbol":"BTC","strategy_name":"apex_regime_mm_v2","capital_source":"standalone_canary","portfolio_purpose":"execution_friction_measurement","backend_ledger_path":"data/live/apex_regime_mm/decisions.jsonl","metalabel_mode":"disabled","strategy_params":{"leverage":3.0,"base_order_notional_usd":12.5},"position_policy":{"position_mode":"isolated_one_way_net_inventory","max_positions_per_symbol":1},"risk":{"max_inventory_notional_usd":30.0,"maximum_reserved_margin_usd":10.0},"execution":{"order_type":"paired_post_only_limit","submission_transport":"single_bulk_orders_action","minimum_order_notional_usd":10.0,"quote_refresh_ms":1000,"maximum_book_age_ms":1000,"markout_horizon_ms":1000,"depth_levels":5,"stop_behavior":"cancel_all_then_taker_flatten_verify_flat"},"regime_policy":{"engine":"not_used_for_market_maker_entries","classification":"NOT_CLASSIFIED"},"runtime":{"purpose":"execution_friction_measurement","offline_edge_status":"not_demonstrated"}}}
{"schema_version":1,"sequence":2,"event_type":"fee","observed_at_utc":"2026-08-01T12:00:00.05+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"maker_rate":0.00015,"taker_rate":0.00045}}
{"schema_version":1,"sequence":3,"event_type":"reconciliation","observed_at_utc":"2026-08-01T12:00:00.1+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"account_value_usd":150.0,"withdrawable_usd":145.0,"open_order_ids":[101,102],"open_orders":[],"fill_ids":[101]}}
{"schema_version":1,"sequence":4,"event_type":"position","observed_at_utc":"2026-08-01T12:00:00.2+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"size_signed":0.0002,"entry_price":65000.0,"margin_used_usd":4.333,"position_value_usd":13.0,"unrealized_pnl_usd":0.05,"leverage_type":"isolated","leverage":3}}
{"schema_version":1,"sequence":5,"event_type":"book_observation","observed_at_utc":"2026-08-01T12:00:00.3+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"source":"hyperliquid_mainnet_l2_rest","exchange_ts_ms":1785585600300,"recv_ts_ms":1785585600310,"mid_px":65000.5,"spread_bps":0.1538,"bid_depth_ratio":1.5,"opi":0.2,"bids":[{"price":65000.0,"size":1.0}],"asks":[{"price":65001.0,"size":0.5}]}}
{"schema_version":1,"sequence":6,"event_type":"theoretical_quote","observed_at_utc":"2026-08-01T12:00:00.4+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","active":true,"reason":"active","fair_value":65000.7,"bid_price":64987.0,"ask_price":65014.0,"bid_size":0.00015,"ask_size":0.00023,"full_spread_bps":4.15,"inventory_utilization":0.433,"inventory_notional_usd":13.0}}
{"schema_version":1,"sequence":7,"event_type":"state_transition","observed_at_utc":"2026-08-01T12:00:00.5+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","state":"INVENTORY","bid_oid":101,"ask_oid":102,"position_size_signed":0.0002,"quote_started_at_ms":1785585600500,"last_fault":null}}
{"schema_version":1,"sequence":8,"event_type":"order_intent","observed_at_utc":"2026-08-01T12:00:00.51+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","operation":"maker_quote","side":"buy","quantity_or_notional":12.5,"limit_price":64987.0}}
{"schema_version":1,"sequence":9,"event_type":"order_acknowledgement","observed_at_utc":"2026-08-01T12:00:00.55+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","operation":"quote_buy","accepted":true,"oid":101,"status":"resting","round_trip_latency_ms":40}}
{"schema_version":1,"sequence":10,"event_type":"fill","observed_at_utc":"2026-08-01T12:00:00.6+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"oid":101,"venue_timestamp_ms":1785585600600,"price":64987.0,"size":0.00015,"side":"B","direction":"Open Long","closed_pnl_usd":0.0,"crossed":false,"fee_usd":0.0015,"fee_token":"USDC"}}
{"schema_version":1,"sequence":11,"event_type":"fee","observed_at_utc":"2026-08-01T12:00:00.61+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"source":"fill","oid":101,"fee_usd":0.0015,"fee_token":"USDC"}}
{"schema_version":1,"sequence":12,"event_type":"execution_quality","observed_at_utc":"2026-08-01T12:00:00.62+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","oid":101,"expected_quote_price":64987.0,"fill_price":64987.0,"fill_size":0.00015,"fill_side":"B","liquidity_side":"maker","slippage_bps":0.0}}
{"schema_version":1,"sequence":13,"event_type":"funding","observed_at_utc":"2026-08-01T12:00:00.7+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"usdc_delta":-0.01,"funding_rate":0.0001,"position_size_signed":0.0002}}
{"schema_version":1,"sequence":14,"event_type":"liquidation_price","observed_at_utc":"2026-08-01T12:00:00.8+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"value":45000.0}}
{"schema_version":1,"sequence":15,"event_type":"liquidation_distance","observed_at_utc":"2026-08-01T12:00:00.9+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","side":"long","mark_price":65000.5,"liquidation_price":45000.0,"distance_pct":30.77}}
{"schema_version":1,"sequence":16,"event_type":"fill_markout","observed_at_utc":"2026-08-01T12:00:01.6+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","oid":101,"fill_timestamp_ms":1785585600600,"fill_price":64987.0,"fill_size":0.00015,"fill_side":"B","liquidity_side":"maker","mark_timestamp_ms":1785585601600,"mark_price":64990.0,"horizon_ms":1000,"markout_bps":0.46163}}"#
}

fn render_strategy_tab(tab: usize) -> String {
    render_strategy_tab_at(tab, 180)
}

fn render_strategy_tab_at(tab: usize, width: u16) -> String {
    let telemetry =
        parse_backend_telemetry(strategy_view_ledger()).expect("strategy view telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = tab;
    let backend = TestBackend::new(width, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Apex MM tab");
    rendered(&terminal)
}

#[test]
fn mm_dashboard_explains_the_strategy_flow_at_standard_width() {
    let dashboard = render_strategy_tab_at(0, 140);

    assert!(dashboard.contains("INPUT: LIVE BTC L2 BOOK"), "{dashboard}");
    assert!(
        dashboard.contains("DECISION: NO DIRECTION CALL"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("ORDERS: ONE BATCHED POST-ONLY BUY + SELL ACTION"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("FIRST FILL: BUY -> TEMP LONG"),
        "{dashboard}"
    );
    assert!(
        dashboard.contains("EXIT/RISK: SKEW QUOTES TOWARD FLAT"),
        "{dashboard}"
    );
    assert!(dashboard.contains("NO TP/SL"), "{dashboard}");
}

fn render_strategy_help() -> String {
    let telemetry =
        parse_backend_telemetry(strategy_view_ledger()).expect("strategy help telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.show_help_overlay = true;
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Apex MM help");
    rendered(&terminal)
}

#[test]
fn mm_dashboard_uses_inventory_and_execution_measurement_semantics() {
    let dashboard = render_strategy_tab(0);

    assert!(
        dashboard.contains("LIVE BTC MARKET-MAKING CANARY"),
        "{dashboard}"
    );
    assert!(dashboard.contains("NOT HYPERVELOCITY"), "{dashboard}");
    assert!(dashboard.contains("NO LONG/SHORT FORECAST"), "{dashboard}");
    assert!(dashboard.contains("REGIME NOT USED"), "{dashboard}");
    assert!(dashboard.contains("PROFIT EDGE UNPROVEN"), "{dashboard}");
    assert!(dashboard.contains("FIRST FILL:"), "{dashboard}");
    assert!(dashboard.contains("NET INVENTORY"), "{dashboard}");
    assert!(dashboard.contains("NOW: LONG INVENTORY"), "{dashboard}");
    assert!(dashboard.contains("PRICES: fair value"), "{dashboard}");
    assert!(dashboard.contains("NEXT:"), "{dashboard}");
    assert!(dashboard.contains("LOSS RESPONSE"), "{dashboard}");
    assert!(dashboard.contains("NO FIXED TP"), "{dashboard}");
    assert!(dashboard.contains("ACCOUNT EQUITY $150.00"), "{dashboard}");
    assert!(dashboard.contains("MAKER FILLS 1"), "{dashboard}");
    assert!(dashboard.contains("FEES $0.0015"), "{dashboard}");
    assert!(
        dashboard.contains("RECENT MM EXECUTION EVENTS"),
        "{dashboard}"
    );
    assert!(!dashboard.contains("LIVE PAPER JOURNAL"), "{dashboard}");
    assert!(!dashboard.contains("WIN RATE"), "{dashboard}");
    assert!(
        !dashboard.contains("TRANSITION DISTRIBUTION"),
        "{dashboard}"
    );
    assert!(!dashboard.contains("AWAITING TP"), "{dashboard}");
}

#[test]
fn mm_dashboard_labels_stale_backend_without_claiming_reconciliation() {
    let mut telemetry =
        parse_backend_telemetry(strategy_view_ledger()).expect("strategy view telemetry");
    telemetry.connection = BackendConnectionState::Stale;
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw stale Apex MM dashboard");
    let dashboard = rendered(&terminal);

    assert!(
        dashboard.contains("BACKEND STALE  |  ENGINE INVENTORY"),
        "{dashboard}"
    );
    assert!(dashboard.contains("TUI CANNOT CONFIRM"), "{dashboard}");
    assert!(!dashboard.contains("BACKEND RECONCILED"), "{dashboard}");
}

#[test]
fn mm_screen_two_is_microstructure_not_a_regime_detector() {
    let screen = render_strategy_tab(1);

    assert!(
        screen.contains("APEX MM MICROSTRUCTURE TELEMETRY"),
        "{screen}"
    );
    assert!(
        screen.contains("NO DIRECTIONAL REGIME AUTHORITY"),
        "{screen}"
    );
    assert!(screen.contains("MID $65000.50"), "{screen}");
    assert!(screen.contains("SPREAD 0.15 bps"), "{screen}");
    assert!(screen.contains("ORDER PRESSURE +0.20"), "{screen}");
    assert!(screen.contains("PAIRED QUOTES"), "{screen}");
    assert!(screen.contains("RECENT MM EXECUTION EVENTS"), "{screen}");
    assert!(!screen.contains("MTF HYSTERESIS"), "{screen}");
    assert!(!screen.contains("HISTORICAL REGIME"), "{screen}");
    assert!(!screen.contains("BBWP"), "{screen}");
}

#[test]
fn mm_chart_overlays_owned_quotes_without_directional_indicators() {
    let chart = render_strategy_tab(2);

    assert!(chart.contains("LIVE L2 MIDPOINT TAPE"), "{chart}");
    assert!(chart.contains("APEX MM QUOTE LEVELS"), "{chart}");
    assert!(chart.contains("BID #101"), "{chart}");
    assert!(chart.contains("ASK #102"), "{chart}");
    assert!(chart.contains("REGIME NOT USED"), "{chart}");
    assert!(!chart.contains("ENTRY ELIGIBILITY"), "{chart}");
    assert!(!chart.contains("BBWP"), "{chart}");
}

#[test]
fn mm_config_exposes_measurement_purpose_without_shadow_controls() {
    let config = render_strategy_tab(3);

    assert!(config.contains("Execution purpose"), "{config}");
    assert!(
        config.contains("execution_friction_measurement"),
        "{config}"
    );
    assert!(config.contains("Regime authority"), "{config}");
    assert!(config.contains("NOT_CLASSIFIED"), "{config}");
    assert!(config.contains("Profitability status"), "{config}");
    assert!(config.contains("not_demonstrated"), "{config}");
    assert!(!config.contains("Shadow reset"), "{config}");
}

#[test]
fn mm_navigation_and_help_describe_the_execution_measurement_strategy() {
    let dashboard = render_strategy_tab(0);
    assert!(dashboard.contains("[2] MICROSTRUCTURE"), "{dashboard}");
    assert!(dashboard.contains("QUOTE: 1000ms"), "{dashboard}");
    assert!(dashboard.contains("MM EVENTS 10"), "{dashboard}");
    assert!(!dashboard.contains("Select Trade"), "{dashboard}");

    let help = render_strategy_help();
    assert!(
        help.contains("APEX MM EXECUTION MEASUREMENT HELP"),
        "{help}"
    );
    assert!(
        help.contains("REGIME: not used for quote decisions"),
        "{help}"
    );
    assert!(
        help.contains("ORDERS: one batched post-only buy + sell action"),
        "{help}"
    );
    assert!(help.contains("TUI AUTHORITY: read only"), "{help}");
    assert!(!help.contains("CANONICAL REGIME POLICY"), "{help}");
}

#[test]
fn projects_mm_fault_message_without_a_success_shaped_fallback() {
    let ledger = r#"{"schema_version":1,"sequence":1,"event_type":"fault","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","message":"paired quote reconciliation failed"}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("fault telemetry");

    assert_eq!(
        telemetry.latest_fault.as_deref(),
        Some("paired quote reconciliation failed")
    );
}

#[test]
fn mm_config_screen_exposes_the_effective_canary_contract() {
    let ledger = r#"{"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"apex_regime_mm_canary_v1","run_id":"apex-mm-live-1","payload":{"symbol":"BTC","strategy_name":"apex_regime_mm_v2","strategy_params":{"leverage":3.0,"base_order_notional_usd":12.5},"position_policy":{"position_mode":"isolated_one_way_net_inventory","max_positions_per_symbol":1},"risk":{"max_inventory_notional_usd":30.0,"maximum_reserved_margin_usd":10.0},"execution":{"order_type":"paired_post_only_limit","submission_transport":"single_bulk_orders_action","minimum_order_notional_usd":10.0,"quote_refresh_ms":1000,"maximum_book_age_ms":1000,"markout_horizon_ms":1000,"depth_levels":5,"stop_behavior":"cancel_all_then_taker_flatten_verify_flat"}}}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("MM config telemetry");

    let rows = backend_config_rows(&telemetry);

    assert!(
        rows.iter()
            .any(|row| row.option == "Base quote" && row.value == "$12.50")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Venue min order" && row.value == "$10.00")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Max inventory" && row.value == "$30.00")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Quote refresh" && row.value == "1000.0ms")
    );
    assert!(rows.iter().any(|row| {
        row.option == "Submission transport" && row.value == "single_bulk_orders_action"
    }));
    assert!(
        rows.iter()
            .any(|row| row.option == "Book freshness" && row.value == "1000.0ms")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Markout horizon" && row.value == "1000.0ms")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "L2 depth" && row.value == "5.0 levels")
    );
    assert!(rows.iter().any(|row| {
        row.option == "Stop behavior" && row.value == "cancel_all_then_taker_flatten_verify_flat"
    }));
}

#[test]
fn projects_explicit_mm_slippage_and_liquidation_distance() {
    let ledger = r#"{"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"symbol":"BTC","strategy_name":"apex_regime_mm_v2"}}
{"event_type":"order_acknowledgement","observed_at_utc":"2026-08-01T12:00:00.050+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","operation":"quote_buy","oid":101,"round_trip_latency_ms":50}}
{"event_type":"execution_quality","observed_at_utc":"2026-08-01T12:00:01+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","oid":101,"expected_quote_price":65000.0,"fill_price":65001.0,"slippage_bps":0.153846}}
{"event_type":"liquidation_distance","observed_at_utc":"2026-08-01T12:00:02+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","side":"long","mark_price":65010.0,"liquidation_price":45000.0,"distance_pct":30.77988}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("execution quality telemetry");

    assert_eq!(telemetry.apex_mm.latest_slippage_bps, Some(0.153846));
    assert_eq!(telemetry.apex_mm.liquidation_distance_pct, Some(30.77988));
    assert_eq!(telemetry.apex_mm.latest_ack_latency_ms, Some(50));
}

#[test]
fn later_empty_reconciliation_clears_stale_owned_quote_ids() {
    let ledger = r#"{"event_type":"configuration_identity","observed_at_utc":"2026-08-01T12:00:00+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"strategy_name":"apex_regime_mm_v2"}}
{"event_type":"state_transition","observed_at_utc":"2026-08-01T12:00:01+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"strategy_id":"apex_regime_mm_v2","state":"QUOTING","bid_oid":101,"ask_oid":102}}
{"event_type":"reconciliation","observed_at_utc":"2026-08-01T12:00:02+00:00","execution_mode":"live","run_id":"apex-mm-live-1","payload":{"account_value_usd":150.0,"open_order_ids":[]}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("reconciled MM telemetry");

    assert_eq!(telemetry.apex_mm.bid_oid, None);
    assert_eq!(telemetry.apex_mm.ask_oid, None);
}
