//! Backend-authoritative liquidation telemetry projection tests.

use hypervector_tui::{app::App, backend_telemetry::parse_backend_telemetry};
use ratatui::{Terminal, backend::TestBackend};

fn render_dashboard(app: &App) -> String {
    let backend = TestBackend::new(180, 50);
    let mut terminal = Terminal::new(backend).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw dashboard");
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

#[test]
fn active_position_displays_backend_liquidation_price() {
    let ledger = r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_params":{"leverage":40.0},"costs":{"maker_fee_rate":0.00015},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-27T12:00:00Z","action":"enter_long","run_id":"hv","symbol":"BTC","fill_px":100.0,"fill_qty":1.0,"position_qty":1.0,"position_avg_px":100.0,"liquidation_price":97.5,"equity":9998.5,"realized_pnl":-1.5,"unrealized_pnl":0.0,"fee_usd":1.5,"leverage":40.0}
{"feed_ts":"2026-07-27T12:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_UP","state_1m":"TREND_UP","state_5m":"TREND_UP","context_15m":"TREND_UP","mark_px":101.0,"position_qty":1.0,"position_avg_px":100.0,"liquidation_price":97.5,"equity":9999.5,"realized_pnl":-1.5,"unrealized_pnl":1.0}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("liquidation telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);

    let rendered = render_dashboard(&app);

    assert!(rendered.contains("LIQ PRICE  $97.50"), "{rendered}");
    assert!(rendered.contains("SOURCE  BACKEND ISOLATED"), "{rendered}");
}

#[test]
fn active_position_does_not_invent_missing_liquidation_price() {
    let ledger = r#"{"feed_ts":"session_start","action":"session_start","run_id":"hv","strategy_params":{"leverage":40.0},"init_cash":10000.0,"equity":10000.0,"position_qty":0.0}
{"feed_ts":"2026-07-27T12:00:00Z","action":"enter_short","run_id":"hv","symbol":"BTC","fill_px":100.0,"fill_qty":1.0,"position_qty":-1.0,"position_avg_px":100.0,"equity":9998.5,"realized_pnl":-1.5,"unrealized_pnl":0.0,"fee_usd":1.5,"leverage":40.0}
{"feed_ts":"2026-07-27T12:01:00Z","action":"regime_observation","run_id":"hv","primary_regime":"TREND_DOWN","state_1m":"TREND_DOWN","state_5m":"TREND_DOWN","context_15m":"TREND_DOWN","mark_px":99.0,"position_qty":-1.0,"position_avg_px":100.0,"equity":9999.5,"realized_pnl":-1.5,"unrealized_pnl":1.0}"#;
    let telemetry = parse_backend_telemetry(ledger).expect("legacy telemetry");
    let mut app = App::new("BTC".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);

    let rendered = render_dashboard(&app);

    assert!(rendered.contains("LIQ PRICE  UNAVAILABLE"), "{rendered}");
    assert!(!rendered.contains("SOURCE  BACKEND ISOLATED"), "{rendered}");
}
