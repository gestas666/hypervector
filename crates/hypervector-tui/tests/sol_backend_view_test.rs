//! SOL backend-ledger acceptance tests for the read-only TUI.

use clap::Parser;
use hypervector_tui::{
    App, CliArgs, backend_telemetry::parse_backend_telemetry, config_view::backend_config_rows,
};
use ratatui::{Terminal, backend::TestBackend};

const SOL_LEDGER: &str = r#"{"feed_ts":"session_start","action":"session_start","run_id":"sol-canary","profile_id":"sol_range_onset_canary_v1","capital_source":"standalone_canary","portfolio_purpose":"canary_validation","backend_ledger_path":"data/research/forward/sol_range_onset_canary/decisions.jsonl","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","execution_mode":"shadow","symbol":"SOL","wallet_configured":true,"signing_key_configured":true,"live_enabled":false,"live_armed":false,"metalabel_mode":"off","strategy_params":{"leverage":5.0},"position_policy":{"position_mode":"isolated_one_way","max_positions_per_symbol":1},"risk":{"margin_fraction":0.03,"max_notional_usd":22.5},"exits":{"mode":"protective_stop_or_signal_or_maximum_hold","stop_bps":80.0,"maximum_hold_seconds":172800.0},"init_cash":150.0,"equity":150.0}
{"feed_ts":"2026-07-31T10:00:00Z","action":"regime_observation","run_id":"sol-canary","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","execution_mode":"shadow","symbol":"SOL","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_DOWN","confidence":0.78,"structural_direction":"short","entry_direction":null,"entry_allowed":false,"regime_admitted":true,"decision_action":"hold","regime_reason":"5m_range_admitted","mark_px":73.49,"open":73.40,"high":73.55,"low":73.35,"volume":1234.0,"position_qty":0.0,"realized_pnl":0.0,"unrealized_pnl":0.0,"equity":150.0}"#;

const LIVE_EVENT_LEDGER: &str = r#"{"schema_version":1,"sequence":1,"event_type":"session_start","observed_at_utc":"2026-07-31T12:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"state":"PREFLIGHT"}}
{"schema_version":1,"sequence":2,"event_type":"configuration_identity","observed_at_utc":"2026-07-31T12:00:01+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"symbol":"SOL","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","capital_source":"standalone_canary","portfolio_purpose":"canary_validation","backend_ledger_path":"data/live/sol_range_onset_canary/decisions.jsonl","metalabel_mode":"off","wallet_configured":true,"signing_key_configured":true,"strategy_params":{"leverage":5.0},"position_policy":{"position_mode":"isolated_one_way","max_positions_per_symbol":1},"risk":{"margin_fraction":0.03,"max_notional_usd":22.5},"exits":{"stop_bps":80.0,"maximum_hold_seconds":172800.0},"execution":{"order_type":"market","time_in_force":"ioc"}}}
{"schema_version":1,"sequence":3,"event_type":"fee","observed_at_utc":"2026-07-31T12:00:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"maker_rate":0.00015,"taker_rate":0.00045}}
{"schema_version":1,"sequence":4,"event_type":"regime_decision","observed_at_utc":"2026-07-31T12:05:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"decision_time_ms":1785499500000,"reference_price":73.10,"long_entry":true,"short_entry":false,"long_exit":false,"short_exit":false,"primary_regime":"BREAKOUT","state_1m":"BREAKOUT","state_5m":"TREND_UP","context_15m":"TREND_UP","confidence":0.82,"structural_direction":"long","regime_admitted":true,"decision_action":"enter_long"}}
{"schema_version":1,"sequence":5,"event_type":"fill","observed_at_utc":"2026-07-31T12:05:01+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"oid":101,"venue_timestamp_ms":1785499501000,"price":73.10,"size":0.30,"side":"B","direction":"Open Long","closed_pnl_usd":0.0,"crossed":true,"transaction_hash":"0xfill","fee_usd":0.00987,"fee_token":"USDC"}}
{"schema_version":1,"sequence":6,"event_type":"position","observed_at_utc":"2026-07-31T12:05:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"size_signed":0.30,"entry_price":73.10,"margin_used_usd":4.386,"position_value_usd":21.93,"unrealized_pnl_usd":0.12,"leverage_type":"isolated","leverage":5.0}}
{"schema_version":1,"sequence":7,"event_type":"liquidation_price","observed_at_utc":"2026-07-31T12:05:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"value":58.25}}
{"schema_version":1,"sequence":8,"event_type":"reconciliation","observed_at_utc":"2026-07-31T12:05:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"account_value_usd":150.12,"withdrawable_usd":145.61,"open_order_ids":[202],"open_orders":[{"oid":202,"size":0.30,"side":"A","reduce_only":true,"is_trigger":true,"trigger_price":72.515,"order_type":"Stop Market"}],"fill_ids":[101]}}
{"schema_version":1,"sequence":9,"event_type":"funding","observed_at_utc":"2026-07-31T13:00:00+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"venue_timestamp_ms":1785502800000,"usdc_delta":-0.01234,"position_size_signed":0.30,"funding_rate":0.000056,"transaction_hash":"0xfunding"}}
{"schema_version":1,"sequence":10,"event_type":"state_transition","observed_at_utc":"2026-07-31T13:00:01+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"state":"OPEN","entry_oid":101,"stop_oid":202,"close_oid":null,"position_size_signed":0.30,"opened_at_ms":1785499500000,"last_fault":null,"stop_reason":null}}
{"schema_version":1,"sequence":11,"event_type":"book_observation","observed_at_utc":"2026-07-31T13:00:02+00:00","execution_mode":"live","effective_mode":"LIVE ARMED","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","profile_fingerprint":"profile","run_fingerprint":"run","run_id":"sol-live","payload":{"source":"hyperliquid_mainnet_l2_rest","exchange_ts_ms":1785502802000,"recv_ts_ms":1785502802010,"mid_px":73.675,"spread_bps":1.3577,"bid_depth_ratio":1.6667,"opi":0.25,"bids":[{"price":73.67,"size":10.0}],"asks":[{"price":73.68,"size":6.0}]}}"#;

#[test]
fn cli_accepts_an_explicit_backend_ledger() {
    let args = CliArgs::try_parse_from([
        "tui-regime-detector",
        "--backend-ledger",
        "data/research/forward/sol/telemetry.jsonl",
    ])
    .expect("CLI args");

    assert_eq!(
        args.backend_ledger.as_deref(),
        Some(std::path::Path::new(
            "data/research/forward/sol/telemetry.jsonl"
        ))
    );
}

#[test]
fn sol_ledger_is_authoritative_for_symbol_and_decision_state() {
    let telemetry = parse_backend_telemetry(SOL_LEDGER).expect("SOL telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);

    app.apply_backend_telemetry(telemetry);

    assert_eq!(app.symbol, "SOL");
    assert_eq!(app.backend.symbol.as_deref(), Some("SOL"));
    assert_eq!(app.backend.regime_admitted, Some(true));
    assert_eq!(app.backend.latest_decision_action.as_deref(), Some("hold"));
}

#[test]
fn observer_row_without_session_start_still_projects_frozen_config() {
    let ledger = r#"{"feed_ts":"2026-07-31T10:00:00Z","action":"regime_observation","run_id":"observer","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","execution_mode":"shadow","symbol":"SOL","strategy_params":{"leverage":5.0},"risk":{"margin_fraction":0.03,"max_notional_usd":2250.0},"exits":{"stop_bps":60.0},"primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_DOWN","mark_px":73.49}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("observer telemetry");

    assert_eq!(telemetry.strategy_params["leverage"], 5.0);
    assert_eq!(telemetry.risk["max_notional_usd"], 2250.0);
    assert_eq!(telemetry.exits["stop_bps"], 60.0);
}

#[test]
fn sol_market_position_uses_taker_rate_for_estimated_exit_fee() {
    let ledger = r#"{"feed_ts":"session_start","action":"session_start","run_id":"sol","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","symbol":"SOL","strategy_params":{"leverage":5.0},"execution":{"order_type":"market"},"costs":{"taker_fee_rate":0.00045},"init_cash":15000.0,"equity":15000.0,"position_qty":0.0}
{"feed_ts":"2026-07-31T10:00:00Z","action":"enter_long","run_id":"sol","symbol":"SOL","fill_px":100.0,"fill_qty":2.0,"position_qty":2.0,"position_avg_px":100.0,"equity":14999.91,"realized_pnl":-0.09,"fee_usd":0.09,"leverage":5.0}
{"feed_ts":"2026-07-31T10:00:05Z","action":"shadow_state","run_id":"sol","symbol":"SOL","mark_px":101.0,"position_qty":2.0,"position_avg_px":100.0,"equity":15001.91,"realized_pnl":-0.09,"unrealized_pnl":2.0}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("SOL active telemetry");

    assert!(telemetry.active_position.is_active());
    assert!((telemetry.active_position.estimated_exit_fee_usd - 0.0909).abs() < 1e-9);
}

#[test]
fn dashboard_and_chart_render_sol_without_btc_unit_leakage() {
    let telemetry = parse_backend_telemetry(SOL_LEDGER).expect("SOL telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw dashboard");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("SYMBOL: SOL"));
    assert!(dashboard.contains("SIZE  0.00000 SOL"));
    assert!(dashboard.contains("Size (SOL)"));
    assert!(dashboard.contains("SHADOW PORTFOLIO"));

    app.active_tab = 2;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw chart");
    let chart = rendered(&terminal);
    assert!(chart.contains("SOL 1m"));
    assert!(chart.contains("1h SMA10/30"));
    assert!(!chart.contains("BTC 1m"));
}

#[test]
fn config_masks_env_credentials_and_reports_backend_arm_state() {
    let telemetry = parse_backend_telemetry(SOL_LEDGER).expect("SOL telemetry");

    let rows = backend_config_rows(&telemetry);

    assert!(
        rows.iter()
            .any(|row| { row.option == "Effective arm state" && row.value == "SHADOW" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Position mode" && row.value == "isolated_one_way" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Margin allocation" && row.value == "3.0%" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Max notional" && row.value == "$22.50" })
    );
    assert!(
        rows.iter()
            .any(|row| { row.option == "Protective stop" && row.value == "80.0 bps" })
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Capital source" && row.value == "standalone_canary")
    );
    assert!(
        rows.iter()
            .any(|row| row.option == "Portfolio purpose" && row.value == "canary_validation")
    );
    assert!(rows.iter().any(|row| {
        row.option == "Backend ledger" && row.value.contains("sol_range_onset_canary")
    }));
    assert!(
        rows.iter()
            .any(|row| { row.option == "Wallet (.env)" && row.value == "******** CONFIGURED" })
    );
    assert!(
        rows.iter().any(|row| {
            row.option == "Signing key (.env)" && row.value == "******** CONFIGURED"
        })
    );
    assert!(
        rows.iter()
            .filter(|row| row.category == "Credentials")
            .all(
                |row| !row.value.starts_with("0x") && !row.value.to_lowercase().contains("private")
            )
    );
}

#[test]
fn live_mode_is_visually_distinct_but_only_when_backend_confirms_it() {
    let ledger = SOL_LEDGER
        .replace(
            "\"execution_mode\":\"shadow\"",
            "\"execution_mode\":\"live\"",
        )
        .replace(
            "\"live_enabled\":false,\"live_armed\":false",
            "\"live_enabled\":true,\"live_armed\":true",
        );
    let telemetry = parse_backend_telemetry(&ledger).expect("live telemetry");
    let mut app = App::new("SOL".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw live dashboard");

    assert!(rendered(&terminal).contains("LIVE ACCOUNT PORTFOLIO"));
}

#[test]
fn event_sourced_live_ledger_projects_authoritative_venue_state() {
    let telemetry = parse_backend_telemetry(LIVE_EVENT_LEDGER).expect("live event telemetry");

    assert_eq!(telemetry.execution_mode.as_deref(), Some("live"));
    assert_eq!(telemetry.live_enabled, Some(true));
    assert_eq!(telemetry.live_armed, Some(true));
    assert_eq!(telemetry.symbol.as_deref(), Some("SOL"));
    assert_eq!(telemetry.latest_regime.as_deref(), Some("BREAKOUT"));
    assert_eq!(
        telemetry.latest_decision_action.as_deref(),
        Some("enter_long")
    );
    assert_eq!(telemetry.stats.current_equity, 150.12);
    assert_eq!(telemetry.costs["taker_fee_rate"], 0.00045);
    assert!(telemetry.active_position.is_active());
    assert_eq!(telemetry.active_position.direction, "LONG");
    assert_eq!(telemetry.active_position.symbol, "SOL");
    assert_eq!(telemetry.active_position.size_btc, 0.30);
    assert_eq!(telemetry.active_position.entry_price, 73.10);
    assert_eq!(telemetry.active_position.entry_fee_usd, 0.00987);
    assert_eq!(telemetry.active_position.funding_payment_usd, -0.01234);
    assert_eq!(telemetry.active_position.liquidation_price, Some(58.25));
    assert_eq!(telemetry.live_state.as_deref(), Some("OPEN"));
    assert_eq!(telemetry.protective_stop_oid, Some(202));
    assert_eq!(telemetry.protective_stop_status.as_deref(), Some("RESTING"));
    assert_eq!(telemetry.protective_stop_price, Some(72.515));
    assert_eq!(telemetry.book.as_ref().map(|book| book.opi), Some(0.25));
    assert_eq!(
        telemetry.execution_authority.as_deref(),
        Some("hyperliquid_mainnet")
    );

    let mut app = App::new("SOL".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 52);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw live event dashboard");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("LIFECYCLE OPEN"));
    assert!(dashboard.contains("STOP $72.52 OID 202 RESTING"));
    assert!(dashboard.contains("AUTH HYPERLIQUID MAINNET"));
    assert!(dashboard.contains("FUNDING PAID $0.01"));
}

#[test]
fn live_trade_journal_closes_on_fill_not_order_ack() {
    let ledger = r#"{"event_type":"configuration_identity","observed_at_utc":"2026-07-31T12:00:00+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"symbol":"SOL","strategy_name":"sol_1h_sma10x30_5m_range_or_breakout","strategy_params":{"leverage":5.0}}}
{"event_type":"fill","observed_at_utc":"2026-07-31T12:01:00+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"oid":101,"price":73.10,"size":0.30,"side":"B","direction":"Open Long","closed_pnl_usd":0.0,"fee_usd":0.01}}
{"event_type":"position","observed_at_utc":"2026-07-31T12:01:01+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"size_signed":0.30,"entry_price":73.10,"unrealized_pnl_usd":0.0,"leverage":5.0}}
{"event_type":"funding","observed_at_utc":"2026-07-31T13:00:00+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"usdc_delta":-0.01}}
{"event_type":"close","observed_at_utc":"2026-07-31T13:00:59+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"reason":"signal_exit","intent":true}}
{"event_type":"close","observed_at_utc":"2026-07-31T13:01:00+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"operation":"reduce_only_close","accepted":true,"oid":303,"status":"filled","filled_size":0.30,"average_price":72.00}}
{"event_type":"fill","observed_at_utc":"2026-07-31T13:01:01+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"oid":303,"price":72.00,"size":0.30,"side":"A","direction":"Close Long","closed_pnl_usd":-0.33,"fee_usd":0.01}}
{"event_type":"position","observed_at_utc":"2026-07-31T13:01:02+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"size_signed":0.0,"entry_price":null,"unrealized_pnl_usd":0.0,"leverage":null}}
{"event_type":"reconciliation","observed_at_utc":"2026-07-31T13:01:02+00:00","execution_mode":"live","live_armed":true,"execution_authority":"hyperliquid_mainnet","profile_id":"sol_range_onset_canary_v1","run_id":"sol-close","payload":{"account_value_usd":149.64,"withdrawable_usd":149.64,"open_orders":[]}}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("live close telemetry");

    assert_eq!(telemetry.trades.len(), 1);
    let trade = &telemetry.trades[0];
    assert_eq!(trade.exit_price, 72.0);
    assert_eq!(trade.pnl_usd, -0.33);
    assert_eq!(trade.entry_fee_usd, 0.01);
    assert_eq!(trade.exit_fee_usd, 0.01);
    assert_eq!(trade.funding_payment_usd, -0.01);
    assert_eq!(trade.total_cost_usd, 0.03);
    assert_eq!(trade.exit_reason, "signal_exit");
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
