//! Unit tests for Quant TA & Microstructure Regime Detector Cockpit.

use hypervector_tui::{
    app::App,
    data_loader::{generate_synthetic_history, parse_snapshot_json},
    model::{RegimeSnapshot, RegimeState},
};

fn make_snapshot(price: f64, high: f64, low: f64, state: RegimeState, ts: &str) -> RegimeSnapshot {
    RegimeSnapshot {
        timestamp_str: ts.to_string(),
        timestamp_ms: 1_784_850_000_000,
        price,
        high,
        low,
        volume: 10.0,
        state,
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
fn test_playhead_aware_split_tp_trade() {
    // Bars 0-4 chop, bull transition at bar 5 (entry 100.0), TP barrier at
    // 100.2 (8% margin at 40x = 0.2% price move) crossed on bar 7.
    let mut snaps: Vec<RegimeSnapshot> = Vec::new();
    for i in 0..5 {
        snaps.push(make_snapshot(100.0, 100.02, 99.98, RegimeState::RangeChop, &format!("2026-07-21 11:0{} :00 UTC", i)));
    }
    snaps.push(make_snapshot(100.0, 100.05, 99.97, RegimeState::BullMomentum, "2026-07-21 11:05:00 UTC"));
    snaps.push(make_snapshot(100.1, 100.15, 100.0, RegimeState::BullMomentum, "2026-07-21 11:06:00 UTC"));
    snaps.push(make_snapshot(100.22, 100.25, 100.05, RegimeState::BullMomentum, "2026-07-21 11:07:00 UTC"));
    snaps.push(make_snapshot(100.2, 100.24, 100.1, RegimeState::BullMomentum, "2026-07-21 11:08:00 UTC"));

    let mut app = App::new("BTC".into(), "1m".into(), snaps, false, true);

    // Playhead at bar 0: the transition has not happened yet, no trades.
    assert!(app.hv_trades.is_empty());
    assert!(app.paper_trades.is_empty());
    assert_eq!(app.paper_stats.total_trades, 0);
    assert!(!app.active_position.is_active());

    // Move playhead to the end: exactly one long, closed by split TP.
    app.current_index = app.snapshots.len() - 1;
    app.refresh_playhead_state();

    assert_eq!(app.hv_trades.len(), 1);
    let trade = &app.hv_trades[0];
    assert_eq!(trade.direction, "LONG");
    assert_eq!(trade.exit_reason, "tp1+tp2");

    // Blended margin: 0.63 * 8.0 + 0.37 * 6.5 = 7.445%
    assert!((trade.margin_pnl_pct - 7.445).abs() < 0.01, "got {}", trade.margin_pnl_pct);

    // PnL on 25% equity margin: 2500 * 7.445% = 186.125 USD
    assert!((trade.pnl_usd - 186.125).abs() < 0.5, "got {}", trade.pnl_usd);
    assert_eq!(app.paper_stats.total_trades, 1);
    assert_eq!(app.paper_stats.wins, 1);
    assert!(!app.active_position.is_active(), "closed trade must leave position flat");
    assert_eq!(app.equity_history.len(), 2);
}

#[test]
fn test_playhead_sl_then_open_position() {
    // Bear transition at bar 2 (short entry 100.0, SL barrier 100.05 hit on
    // bar 3), then bull transition at bar 4 whose long never hits a barrier
    // and stays open at the playhead.
    let snaps = vec![
        make_snapshot(100.0, 100.01, 99.99, RegimeState::RangeChop, "2026-07-21 11:00:00 UTC"),
        make_snapshot(100.0, 100.01, 99.99, RegimeState::RangeChop, "2026-07-21 11:01:00 UTC"),
        make_snapshot(100.0, 100.02, 99.98, RegimeState::BearMomentum, "2026-07-21 11:02:00 UTC"),
        make_snapshot(100.04, 100.06, 99.99, RegimeState::BearMomentum, "2026-07-21 11:03:00 UTC"),
        make_snapshot(100.0, 100.02, 99.98, RegimeState::BullMomentum, "2026-07-21 11:04:00 UTC"),
        make_snapshot(100.05, 100.08, 99.99, RegimeState::BullMomentum, "2026-07-21 11:05:00 UTC"),
        make_snapshot(100.1, 100.12, 100.0, RegimeState::BullMomentum, "2026-07-21 11:06:00 UTC"),
    ];

    let mut app = App::new("BTC".into(), "1m".into(), snaps, false, true);
    app.current_index = app.snapshots.len() - 1;
    app.refresh_playhead_state();

    assert_eq!(app.hv_trades.len(), 2);
    assert_eq!(app.hv_trades[0].direction, "SHORT");
    assert_eq!(app.hv_trades[0].exit_reason, "SL");
    assert!((app.hv_trades[0].margin_pnl_pct - (-2.0)).abs() < 0.01);

    assert_eq!(app.hv_trades[1].direction, "LONG");
    assert_eq!(app.hv_trades[1].exit_reason, "OPEN");

    // Open trade stays unrealised: stats only count the closed short.
    assert_eq!(app.paper_stats.total_trades, 1);
    assert_eq!(app.paper_stats.losses, 1);
    assert!(app.paper_stats.unrealized_pnl > 0.0);
    assert!(app.active_position.is_active());
    assert_eq!(app.active_position.direction, "LONG");

    // Rewind before the bull transition: only the short remains visible.
    app.current_index = 3;
    app.refresh_playhead_state();
    assert_eq!(app.hv_trades.len(), 1);
    assert_eq!(app.hv_trades[0].exit_reason, "SL");
}
