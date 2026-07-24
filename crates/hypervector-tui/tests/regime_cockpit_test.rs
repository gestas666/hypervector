//! Unit tests for Quant TA & Microstructure Regime Detector Cockpit.

use hypervector_tui::{
    app::App,
    data_loader::generate_synthetic_history,
    model::RegimeState,
};

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
