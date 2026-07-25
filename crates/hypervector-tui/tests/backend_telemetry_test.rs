//! Backend shadow-ledger telemetry contract for the read-only TUI.

use std::fs;

use hypervector_tui::backend_telemetry::{
    BackendConnectionState, BackendTelemetrySource, parse_backend_telemetry,
};

#[test]
fn parses_latest_run_into_authoritative_trade_and_model_state() {
    let jsonl = r#"
{"feed_ts":"session_start","action":"session_start","run_id":"old","strategy_name":"crown_stack_long","execution_mode":"shadow","init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-01T00:01:00Z","action":"enter_long","run_id":"old","strategy_name":"crown_stack_long","equity":9999.0,"realized_pnl":-1.0,"position_qty":0.1,"position_avg_px":90.0}
{"feed_ts":"session_start","action":"session_start","run_id":"hv-run","export_id":"hv-export","strategy_name":"hypervelocity_1m_scalper_long","execution_mode":"shadow","metalabel_mode":"observe","metalabel_bundle_id":"hypervelocity-long-v001","conviction":0.5,"strategy_params":{"strategy":"hypervelocity_1m_scalper_long","leverage":40.0,"target_margin_pct":8.0},"exits":{"mode":"strategy_target_only","target_margin_pct":8.0,"stop":null},"risk":{"mode":"fixed_margin_fraction","margin_fraction":0.7,"notional_fraction":28.0},"execution":{"order_type":"limit","time_in_force":"post_only","fill_rule":"through_one_tick","fill_model":"post_only_limit_through_v1","tick_size":1.0,"entry_ttl_seconds":300.0},"costs":{"slippage_bps":2.0},"init_cash":10000.0,"equity":10000.0,"realized_pnl":0.0,"unrealized_pnl":0.0,"position_qty":0.0,"position_avg_px":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"enter_long","run_id":"hv-run","strategy_name":"hypervelocity_1m_scalper_long","symbol":"BTC","fill_px":100.0,"fill_qty":0.1,"position_qty":0.1,"position_avg_px":100.0,"equity":9998.0,"realized_pnl":-2.0,"unrealized_pnl":0.0,"conviction":0.5,"conviction_source":"metalabel_observe","metalabel_p":0.62,"metalabel_bundle_id":"hypervelocity-long-v001","leverage":40.0}
{"feed_ts":"2026-07-25T12:01:00Z","action":"funding","run_id":"hv-run","strategy_name":"hypervelocity_1m_scalper_long","position_qty":0.1,"position_avg_px":100.0,"equity":10003.0,"realized_pnl":-1.0,"unrealized_pnl":4.0}
{"feed_ts":"2026-07-25T12:02:00Z","action":"close","run_id":"hv-run","strategy_name":"hypervelocity_1m_scalper_long","symbol":"BTC","fill_px":102.0,"fill_qty":0.1,"position_qty":0.0,"position_avg_px":0.0,"equity":10018.0,"realized_pnl":18.0,"unrealized_pnl":0.0,"conviction":0.5,"conviction_source":"metalabel_observe","metalabel_p":0.64,"metalabel_bundle_id":"hypervelocity-long-v001","leverage":40.0}
"#;

    let telemetry = parse_backend_telemetry(jsonl).expect("valid backend ledger");

    assert_eq!(telemetry.connection, BackendConnectionState::Connected);
    assert_eq!(telemetry.run_id.as_deref(), Some("hv-run"));
    assert_eq!(telemetry.export_id.as_deref(), Some("hv-export"));
    assert_eq!(
        telemetry.strategy_name.as_deref(),
        Some("hypervelocity_1m_scalper_long")
    );
    assert_eq!(telemetry.execution_mode.as_deref(), Some("shadow"));
    assert_eq!(telemetry.metalabel_mode.as_deref(), Some("observe"));
    assert_eq!(
        telemetry.metalabel_bundle_id.as_deref(),
        Some("hypervelocity-long-v001")
    );
    assert_eq!(
        telemetry.latest_conviction_source.as_deref(),
        Some("metalabel_observe")
    );
    assert_eq!(telemetry.latest_metalabel_p, Some(0.64));
    assert_eq!(telemetry.strategy_params["leverage"], 40.0);
    assert_eq!(telemetry.exits["mode"], "strategy_target_only");
    assert_eq!(telemetry.risk["margin_fraction"], 0.7);
    assert_eq!(telemetry.execution_policy["order_type"], "limit");
    assert_eq!(telemetry.execution_policy["time_in_force"], "post_only");
    assert_eq!(telemetry.execution_policy["fill_rule"], "through_one_tick");
    assert_eq!(telemetry.costs["slippage_bps"], 2.0);
    assert_eq!(telemetry.trades.len(), 1);
    assert_eq!(telemetry.trades[0].direction, "LONG");
    assert!((telemetry.trades[0].pnl_usd - 18.0).abs() < 1e-9);
    assert_eq!(telemetry.stats.total_trades, 1);
    assert_eq!(telemetry.stats.wins, 1);
    assert!((telemetry.stats.current_equity - 10018.0).abs() < 1e-9);
    assert!(!telemetry.active_position.is_active());
    assert_eq!(telemetry.equity_history.last().copied(), Some(10018.0));
}

#[test]
fn source_reports_disconnected_and_error_without_inventing_state() {
    let tmp = tempfile::tempdir().expect("tempdir");
    let path = tmp.path().join("decisions.jsonl");
    let mut source = BackendTelemetrySource::new(path.clone());

    let missing = source.refresh();
    assert_eq!(missing.connection, BackendConnectionState::Disconnected);
    assert!(missing.trades.is_empty());
    assert!(!missing.active_position.is_active());

    fs::write(&path, "{not-json}\n").expect("write malformed ledger");
    let malformed = source.refresh();
    assert_eq!(malformed.connection, BackendConnectionState::Error);
    assert!(malformed.status_message.contains("line 1"));
    assert!(malformed.trades.is_empty());
}

#[test]
fn skipped_entry_is_not_reconstructed_as_a_trade() {
    let jsonl = r#"
{"feed_ts":"session_start","action":"session_start","run_id":"hv-run","init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"enter_long","run_id":"hv-run","skipped":true,"fill_qty":0.0,"equity":10000.0,"realized_pnl":0.0}
{"feed_ts":"2026-07-25T12:01:00Z","action":"close","run_id":"hv-run","fill_px":101.0,"fill_qty":0.1,"position_qty":0.0,"equity":10000.0,"realized_pnl":0.0}
"#;

    let telemetry = parse_backend_telemetry(jsonl).expect("valid backend ledger");

    assert!(telemetry.trades.is_empty());
    assert!(!telemetry.active_position.is_active());
}

#[test]
fn exact_hypervelocity_trade_uses_backend_regime_leverage_and_net_margin_return() {
    let ledger = r#"{"feed_ts":"session_start","action":"session_start","run_id":"7ea893372898","strategy_name":"hypervelocity_1m_scalper","strategy_params":{"leverage":40.0,"target_margin_pct":8.0},"risk":{"margin_fraction":0.7},"init_cash":10000.0,"equity":10000.0,"realized_pnl":0.0}
{"feed_ts":"2026-07-25T13:37:00Z","action":"regime_observation","run_id":"7ea893372898","primary_regime":"TREND_UP","position_qty":0.0,"equity":10000.0,"realized_pnl":0.0}
{"feed_ts":"2026-07-25T13:38:00Z","action":"enter_long","run_id":"7ea893372898","symbol":"BTC","fill_px":64100.0,"fill_qty":4.36817,"fee_usd":41.99995455,"position_qty":4.36817,"position_avg_px":64100.0,"equity":9958.00004545,"realized_pnl":-41.99995455}
{"feed_ts":"2026-07-25T13:50:00Z","action":"close","run_id":"7ea893372898","symbol":"BTC","fill_px":64229.0,"fill_qty":4.36817,"fee_usd":42.0844786395,"position_qty":0.0,"equity":10479.4094968105,"realized_pnl":479.4094968105}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("telemetry");
    let trade = &telemetry.trades[0];

    assert_eq!(telemetry.regime_history, vec!["TREND_UP"]);
    assert!((trade.leverage - 40.0).abs() < 1e-9);
    assert!((trade.pnl_usd - 479.4094968105).abs() < 1e-9);
    assert!((trade.pnl_pct - 6.8487142387).abs() < 1e-6);
}

#[test]
fn projects_backend_regime_history_and_measured_book_telemetry() {
    let ledger = r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0}
{"feed_ts":"2026-07-25T14:00:00Z","action":"regime_observation","run_id":"hv","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"TREND_UP","confidence":0.61,"regime_reason":"5m_primary_state","mark_px":100.0,"high":101.0,"low":99.0,"volume":12.0,"rsi":48.0,"bbwp_percentile":22.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T14:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","entry_direction":"long","entry_allowed":true,"state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","confidence":0.83,"regime_reason":"5m_primary_trend","mark_px":101.0,"high":102.0,"low":100.0,"volume":15.0,"rsi":62.0,"bbwp_percentile":44.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T14:01:05Z","action":"book_observation","run_id":"hv","source":"hl_rest_l2","exchange_ts_ms":1784988065000.0,"recv_ts_ms":1784988065050.0,"mid_px":101.25,"spread_bps":4.9382716,"bid_depth_ratio":2.0,"opi":0.3333333,"bids":[{"price":101.0,"size":4.0}],"asks":[{"price":101.5,"size":2.0}]}"#;

    let telemetry = parse_backend_telemetry(ledger).expect("telemetry");

    assert_eq!(telemetry.regime_snapshots.len(), 2);
    assert_eq!(telemetry.latest_regime.as_deref(), Some("TREND_UP"));
    assert_eq!(telemetry.entry_direction.as_deref(), Some("long"));
    assert_eq!(telemetry.entry_allowed, Some(true));
    assert_eq!(telemetry.regime_snapshots[0].state.primary_label(), "RANGE");
    assert_eq!(
        telemetry.regime_snapshots[1].state.primary_label(),
        "TREND_UP"
    );
    assert_eq!(
        telemetry.regime_snapshots[1].regime_reason,
        "5m_primary_trend"
    );
    let book = telemetry.book.as_ref().expect("book telemetry");
    assert_eq!(book.source, "hl_rest_l2");
    assert!((book.spread_bps - 4.9382716).abs() < 1e-9);
    assert!((book.opi - 0.3333333).abs() < 1e-9);
    assert_eq!(book.bid_levels[0].price, 101.0);
    assert_eq!(book.ask_levels[0].size, 2.0);
}
