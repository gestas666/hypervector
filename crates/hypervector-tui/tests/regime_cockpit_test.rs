//! Unit tests for Quant TA & Microstructure Regime Detector Cockpit.

use hypervector_tui::{
    app::App,
    backend_telemetry::parse_backend_telemetry,
    config_view::backend_config_rows,
    data_loader::{generate_synthetic_history, parse_snapshot_json},
    model::{EngineConfig, RegimeSnapshot, RegimeState, SplitPositionMode},
};
use ratatui::{Terminal, backend::TestBackend};

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
        high,
        low,
        volume: 10.0,
        state,
        regime_reason: "fixture".into(),
        confidence: 0.6,
        opi: 0.1,
        spread_bps: 1.2,
        bid_depth_ratio: 1.1,
        bbwp_percentile: 50.0,
        rsi: 55.0,
        funding_zscore: 0.1,
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
        "close": 66311.0,
        "high": 66320.0,
        "low": 66290.0,
        "volume": 12.4,
        "regime_state": "BEAR_MOMENTUM_EXPANSION",
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

    let snapshot = parse_snapshot_json(&val, 0).expect("snapshot should parse");

    assert_eq!(snapshot.state, RegimeState::BullMomentum);
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

    assert_eq!(config.static_leverage_value, 40.0);
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
fn test_backend_config_is_a_selectable_menu_not_raw_json() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","metalabel_mode":"off","strategy_params":{"leverage":40.0,"target_margin_pct":8.0},"position_policy":{"position_mode":"one_way","max_positions_per_symbol":1},"risk":{"margin_fraction":0.7},"exits":{"target_margin_pct":8.0,"range_policy":"hold_until_target"},"execution":{"order_type":"limit","time_in_force":"post_only","entry_ttl_seconds":300.0},"costs":{"maker_fee_rate":0.00015,"funding_source":"live_meta_and_asset_contexts"},"init_cash":10000.0,"equity":10000.0}"#,
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
    assert!(rows.iter().all(|row| !row.value.contains('{')));
}

#[test]
fn test_dashboard_uses_backend_margin_costs_and_mark_to_market_pnl() {
    let telemetry = parse_backend_telemetry(
        r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_name":"hypervelocity_1m_scalper","execution_mode":"shadow","strategy_params":{"leverage":40.0},"risk":{"margin_fraction":0.7},"execution":{"order_type":"limit","time_in_force":"post_only"},"costs":{"maker_fee_rate":0.00015},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-25T12:00:00Z","action":"enter_short","run_id":"hv","symbol":"BTC","fill_px":64100.0,"fill_qty":4.36817,"position_qty":-4.36817,"position_avg_px":64100.0,"equity":9958.0,"realized_pnl":-42.0,"unrealized_pnl":0.0,"leverage":40.0}
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
    assert!(!rendered.contains("25% Cap"));
    assert!(!rendered.contains("Taker Drag"));
    assert!(!rendered.contains("+$-"));
}
