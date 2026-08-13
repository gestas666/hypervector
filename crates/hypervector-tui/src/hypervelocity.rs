//! Hypervelocity strategy screen backed by authoritative backend telemetry.
//!
//! Renders the strategy command bar, active position telemetry with breathing
//! orderbook depth ladder, and the unified Trade State Tracker dashboard.

#[path = "hypervelocity_command_bar.rs"]
mod hypervelocity_command_bar;
#[path = "hypervelocity_order_book.rs"]
mod hypervelocity_order_book;
#[path = "hypervelocity_position_panel.rs"]
mod hypervelocity_position_panel;
#[path = "hypervelocity_trade_history.rs"]
mod hypervelocity_trade_history;
#[path = "hypervelocity_trade_statistics.rs"]
mod hypervelocity_trade_statistics;

pub use hypervelocity_command_bar::render_command_bar;
pub(crate) use hypervelocity_order_book::render_book_ladder;
pub use hypervelocity_position_panel::render_position_and_book;
pub use hypervelocity_trade_statistics::{
    render_all_time_stats, render_return_distribution, render_run_stats,
    render_trade_state_dashboard,
};

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
};

use crate::app::App;

pub fn render_screen_hypervelocity(f: &mut Frame, app: &App, area: Rect) {
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6),  // Row 1: Strategy Command Bar
            Constraint::Length(11), // Row 2: Active Position + Orderbook Depth Ladder
            Constraint::Min(14),    // Row 3: Trade State Tracker Dashboard
        ])
        .split(area);

    render_command_bar(f, app, main_chunks[0]);
    render_position_and_book(f, app, main_chunks[1]);
    render_trade_state_dashboard(f, app, main_chunks[2]);
}

fn backend_number(value: &serde_json::Value, key: &str) -> Option<f64> {
    value.get(key).and_then(serde_json::Value::as_f64)
}

fn effective_backend_leverage(app: &App) -> Option<f64> {
    if app.active_position.is_active() && app.active_position.leverage > 0.0 {
        Some(app.active_position.leverage)
    } else {
        backend_number(&app.backend.strategy_params, "leverage")
    }
}

fn backend_exit_display(app: &App) -> String {
    let mode = app
        .backend
        .exits
        .get("mode")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("n/a")
        .to_string();
    if mode == "target_or_maximum_hold_no_fixed_stop" {
        "TP OR 24H MAX · NO STOP".to_string()
    } else {
        mode
    }
}
