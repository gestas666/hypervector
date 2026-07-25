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
{"feed_ts":"session_start","action":"session_start","run_id":"hv-run","export_id":"hv-export","strategy_name":"hypervelocity_1m_scalper_long","execution_mode":"shadow","metalabel_mode":"observe","metalabel_bundle_id":"hypervelocity-long-v001","conviction":0.5,"strategy_params":{"strategy":"hypervelocity_1m_scalper_long","leverage":40.0,"target_margin_pct":8.0},"exits":{"mode":"atr","sl_atr_mult":1.5},"risk":{"risk_pct_max":0.05},"costs":{"slippage_bps":2.0},"init_cash":10000.0,"equity":10000.0,"realized_pnl":0.0,"unrealized_pnl":0.0,"position_qty":0.0,"position_avg_px":0.0}
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
    assert_eq!(telemetry.exits["mode"], "atr");
    assert_eq!(telemetry.risk["risk_pct_max"], 0.05);
    assert_eq!(telemetry.costs["slippage_bps"], 2.0);
    assert_eq!(telemetry.trades.len(), 1);
    assert_eq!(telemetry.trades[0].direction, "LONG");
    assert!((telemetry.trades[0].pnl_usd - 20.0).abs() < 1e-9);
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
