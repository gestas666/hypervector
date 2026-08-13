//! Live backend order-book depth ladder.

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use crate::animation;
use crate::app::App;

pub(crate) fn render_book_ladder(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" LIVE L2 DEPTH LADDER ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(book_lines(app)).block(block), area);
}

fn book_lines(app: &App) -> Vec<Line<'static>> {
    let max_size = maximum_depth_size(app);
    let mut lines = Vec::new();
    for index in (0..app.book_state.ask_levels.len()).rev() {
        lines.push(ask_line(app, index, max_size));
    }
    lines.push(spread_line(app));
    for index in 0..app.book_state.bid_levels.len() {
        lines.push(bid_line(app, index, max_size));
    }
    lines.push(telemetry_line(app));
    lines
}

fn maximum_depth_size(app: &App) -> f64 {
    let asks = app
        .book_state
        .ask_levels
        .iter()
        .map(|level| level.size)
        .fold(0.0f64, f64::max);
    let bids = app
        .book_state
        .bid_levels
        .iter()
        .map(|level| level.size)
        .fold(0.0f64, f64::max);
    asks.max(bids).max(0.01)
}

fn ask_line(app: &App, index: usize, max_size: f64) -> Line<'static> {
    let level = &app.book_state.ask_levels[index];
    let base_length = ((level.size / max_size) * 18.0).max(1.0) as usize;
    let breath = animation::bar_breath(app.tick_count, index);
    let flash = animation::depth_flash(
        app.tick_count,
        app.book_state
            .ask_last_change
            .get(index)
            .copied()
            .unwrap_or(0),
    );
    let bar = "█".repeat((base_length as f64 * breath).max(1.0) as usize);
    let color = if flash > 1.0 {
        Style::default().fg(ratatui::style::Color::Rgb(
            (220.0 * flash).min(255.0) as u8,
            (50.0 / flash).max(30.0) as u8,
            (70.0 / flash).max(40.0) as u8,
        ))
    } else {
        app.theme.depth_ask
    };
    Line::from(vec![
        Span::styled(format!("ASK  ${:.2}  ", level.price), app.theme.bear),
        Span::styled(bar, color),
        Span::styled(format!(" {:.2}", level.size), app.theme.muted),
    ])
}

fn bid_line(app: &App, index: usize, max_size: f64) -> Line<'static> {
    let level = &app.book_state.bid_levels[index];
    let base_length = ((level.size / max_size) * 18.0).max(1.0) as usize;
    let breath = animation::bar_breath(app.tick_count, index);
    let flash = animation::depth_flash(
        app.tick_count,
        app.book_state
            .bid_last_change
            .get(index)
            .copied()
            .unwrap_or(0),
    );
    let bar = "█".repeat((base_length as f64 * breath).max(1.0) as usize);
    let color = if flash > 1.0 {
        Style::default().fg(ratatui::style::Color::Rgb(
            0,
            (200.0 * flash).min(255.0) as u8,
            (100.0 / flash).max(60.0) as u8,
        ))
    } else {
        app.theme.depth_bid
    };
    Line::from(vec![
        Span::styled(format!("BID  ${:.2}  ", level.price), app.theme.bull),
        Span::styled(bar, color),
        Span::styled(format!(" {:.2}", level.size), app.theme.muted),
    ])
}

fn spread_line(app: &App) -> Line<'static> {
    let spread = app.book_state.spread_bps;
    let style = if spread <= 3.0 {
        app.theme.bull
    } else if spread <= 6.0 {
        app.theme.coiling
    } else {
        app.theme.bear
    };
    Line::from(vec![Span::styled(
        format!("───── SPREAD {spread:.1} bps ─────"),
        style,
    )])
}

fn telemetry_line(app: &App) -> Line<'static> {
    let bs = &app.book_state;
    let gate_dot = if bs.gate_ok {
        Span::styled("●", app.theme.bull)
    } else {
        Span::styled("◉", app.theme.gate_blocked)
    };
    let opi_arrow = if bs.opi >= 0.0 {
        Span::styled("▲", app.theme.bull)
    } else {
        Span::styled("▼", app.theme.bear)
    };

    Line::from(vec![
        Span::raw("TELEMETRY: "),
        gate_dot,
        Span::styled(
            format!(
                " {}  │  OPI {:.2} ",
                if bs.gate_ok { "LIVE" } else { &bs.gate_reason },
                bs.opi
            ),
            app.theme.muted,
        ),
        opi_arrow,
        Span::raw("  │  "),
        Span::styled("BACKEND L2", app.theme.bull),
    ])
}
