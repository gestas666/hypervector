//! Aggregate trade-state statistics and return distribution.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use super::hypervelocity_trade_history::render_trade_breakdown_and_equity;
use crate::animation;
use crate::app::App;
use crate::model::{HypervelocityTrade, RegimeState};

// ============================================================================
// ROW 3: Trade State Tracker — The Unified Dashboard
// ============================================================================
pub fn render_trade_state_dashboard(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(7), // Stats row (3 columns)
            Constraint::Min(7),    // Per-trade breakdown + equity sparkline
        ])
        .split(area);

    render_stats_row(f, app, chunks[0]);
    render_trade_breakdown_and_equity(f, app, chunks[1]);
}

fn render_stats_row(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(33),
            Constraint::Percentage(34),
            Constraint::Percentage(33),
        ])
        .split(area);

    render_all_time_stats(f, app, chunks[0]);
    render_run_stats(f, app, chunks[1]);
    render_return_distribution(f, app, chunks[2]);
}

pub fn render_all_time_stats(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" ALL-TIME PERFORMANCE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(all_time_lines(app)).block(block), area);
}

fn all_time_lines(app: &App) -> Vec<Line<'static>> {
    let stats = &app.paper_stats;
    let (win_fill, loss_fill) = win_loss_bar(stats.win_rate_pct);
    vec![
        Line::from(vec![
            Span::raw("TRADES  "),
            Span::styled(format!("{}", stats.total_trades), app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("WINS/LOSS  "),
            Span::styled(
                format!("{}/{}  ", stats.wins, stats.losses),
                app.theme.title,
            ),
            Span::styled(win_fill, app.theme.bull),
            Span::styled(loss_fill, app.theme.bear),
        ]),
        Line::from(vec![Span::styled(
            format!("{:.1}% WIN RATE", stats.win_rate_pct),
            win_rate_style(app),
        )]),
        Line::from(vec![
            Span::raw("PF  "),
            Span::styled(profit_factor_label(app), app.theme.gold),
        ]),
        Line::from(vec![Span::styled(
            format!(
                "AVG WIN +${:.2}  │  MAX DD -{:.2}%",
                stats.avg_win_usd, stats.max_drawdown_pct
            ),
            app.theme.muted,
        )]),
    ]
}

fn win_loss_bar(win_rate: f64) -> (String, String) {
    let wins = ((win_rate / 100.0) * 18.0) as usize;
    ("█".repeat(wins), "░".repeat(18 - wins))
}

fn profit_factor_label(app: &App) -> String {
    if app.paper_stats.losses == 0 {
        "∞ (NO LOSSES)".to_string()
    } else {
        format!("{:.2}", app.paper_stats.profit_factor)
    }
}

fn win_rate_style(app: &App) -> Style {
    if app.paper_stats.win_rate_pct < 90.0 {
        return app.theme.bull;
    }
    let pulse = animation::pulse(app.tick_count, 20);
    Style::default()
        .fg(ratatui::style::Color::Rgb(
            (255.0 * (0.85 + 0.15 * pulse)) as u8,
            (215.0 * (0.85 + 0.15 * pulse)) as u8,
            0,
        ))
        .add_modifier(Modifier::BOLD)
}

pub fn render_run_stats(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" THIS RUN PERFORMANCE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(run_stats_lines(app)).block(block), area);
}

fn run_stats_lines(app: &App) -> Vec<Line<'static>> {
    let closed = app.run_position_index;
    vec![
        run_position_line(app, closed),
        run_record_line(app, closed),
        run_pnl_line(app),
        run_margin_line(app),
        run_regime_line(app),
    ]
}

fn run_position_line(app: &App, closed: u32) -> Line<'static> {
    let displayed = closed + u32::from(app.active_position.is_active());
    let (icon, style) = run_direction(app);
    Line::from(vec![
        Span::raw("POSITION  "),
        Span::styled(format!("#{displayed}"), app.theme.gold),
        Span::raw("  "),
        Span::styled(format!("{} {}", icon, app.position_run_direction), style),
    ])
}

fn run_record_line(app: &App, closed: u32) -> Line<'static> {
    let win_rate = if closed > 0 {
        app.run_wins as f64 / closed as f64 * 100.0
    } else {
        0.0
    };
    Line::from(vec![
        Span::raw("W/L RUN   "),
        Span::styled(
            format!(
                "{}W / {}L  ",
                app.run_wins,
                closed.saturating_sub(app.run_wins)
            ),
            app.theme.title,
        ),
        Span::styled(format!("{win_rate:.0}%"), app.theme.bull),
    ])
}

fn run_pnl_line(app: &App) -> Line<'static> {
    let pnl = app.paper_stats.current_equity - app.paper_stats.initial_capital;
    Line::from(vec![
        Span::raw("RUN PNL   "),
        Span::styled(signed_usd(pnl), app.theme.gold),
    ])
}

fn run_margin_line(app: &App) -> Line<'static> {
    Line::from(vec![
        Span::raw("AVG MARGIN "),
        Span::styled(format!("+{:.2}%", average_run_margin(app)), app.theme.cyan),
    ])
}

fn run_regime_line(app: &App) -> Line<'static> {
    let state = app.current_snapshot().state;
    Line::from(vec![
        Span::raw("REGIME    "),
        Span::styled(state.primary_label(), regime_style(app, state)),
    ])
}

fn run_direction(app: &App) -> (&'static str, Style) {
    match app.position_run_direction.as_str() {
        "LONG" => ("▲", app.theme.bull),
        "SHORT" => ("▼", app.theme.bear),
        _ => ("◆", app.theme.muted),
    }
}

fn average_run_margin(app: &App) -> f64 {
    let recent: Vec<&HypervelocityTrade> = app
        .hv_trades
        .iter()
        .rev()
        .take(app.run_position_index as usize)
        .collect();
    if recent.is_empty() {
        0.0
    } else {
        recent.iter().map(|trade| trade.margin_pnl_pct).sum::<f64>() / recent.len() as f64
    }
}

fn regime_style(app: &App, state: RegimeState) -> Style {
    match state {
        RegimeState::BullMomentum => app.theme.bull,
        RegimeState::BearMomentum => app.theme.bear,
        RegimeState::VolatilityCoiling => app.theme.coiling,
        RegimeState::FundingCarry => app.theme.carry,
        RegimeState::RangeChop | RegimeState::Unknown => app.theme.muted,
    }
}

fn signed_usd(value: f64) -> String {
    let normalized = if value.abs() < 0.005 { 0.0 } else { value };
    let sign = if normalized >= 0.0 { "+" } else { "-" };
    format!("{sign}${:.2}", normalized.abs())
}

pub fn render_return_distribution(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" RETURN DISTRIBUTION ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(
        Paragraph::new(return_distribution_lines(app)).block(block),
        area,
    );
}

fn return_buckets(app: &App) -> [usize; 7] {
    let mut buckets = [0usize; 7]; // -2, 0, +2, +4, +6, +8, +10+
    for trade in &app.hv_trades {
        let index = if trade.margin_pnl_pct < -1.0 {
            0
        } else if trade.margin_pnl_pct < 1.0 {
            1
        } else if trade.margin_pnl_pct < 3.0 {
            2
        } else if trade.margin_pnl_pct < 5.0 {
            3
        } else if trade.margin_pnl_pct < 7.0 {
            4
        } else if trade.margin_pnl_pct < 9.0 {
            5
        } else {
            6
        };
        buckets[index] += 1;
    }
    buckets
}

fn return_distribution_lines(app: &App) -> Vec<Line<'static>> {
    let buckets = return_buckets(app);
    let max_bucket = *buckets.iter().max().unwrap_or(&1).max(&1);
    let bar_width = 10usize;
    let labels = ["-2%", "0%", "+2%", "+4%", "+6%", "+8%", "+10%"];
    let colors = [
        app.theme.bear,
        app.theme.muted,
        app.theme.bull,
        app.theme.bull,
        app.theme.gold,
        app.theme.zone_target,
        app.theme.zone_climax,
    ];
    (0..7)
        .map(|index| {
            let bar_len = ((buckets[index] as f64 / max_bucket as f64) * bar_width as f64)
                .max(if buckets[index] > 0 { 1.0 } else { 0.0 }) as usize;
            let bar = "█".repeat(bar_len);
            let empty = "░".repeat(bar_width - bar_len);
            Line::from(vec![
                Span::styled(format!("{:>4} ", labels[index]), app.theme.muted),
                Span::styled(bar, colors[index]),
                Span::styled(empty, app.theme.muted),
                Span::styled(format!(" {}", buckets[index]), app.theme.muted),
            ])
        })
        .collect()
}
