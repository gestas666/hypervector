//! Per-trade history and rolling equity visualization.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Sparkline},
};

use super::{backend_number, effective_backend_leverage};
use crate::animation;
use crate::app::App;
use crate::model::HypervelocityTrade;

pub(super) fn render_trade_breakdown_and_equity(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);

    render_per_trade_breakdown(f, app, chunks[0]);
    render_equity_sparkline(f, app, chunks[1]);
}

fn render_per_trade_breakdown(f: &mut Frame, app: &App, area: Rect) {
    let trades: Vec<&HypervelocityTrade> = app.hv_trades.iter().rev().take(12).collect();
    let max_age = trades.len().max(1);
    let lines = trades
        .iter()
        .enumerate()
        .map(|(age, trade)| trade_line(app, trade, age, max_age))
        .collect::<Vec<_>>();
    let block = Block::default()
        .title(format!(" PER-TRADE BREAKDOWN (last {}) ", trades.len()))
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);

    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn trade_line(app: &App, trade: &HypervelocityTrade, age: usize, max_age: usize) -> Line<'static> {
    let (direction_icon, direction_style) = trade_direction(app, trade);
    let pnl_style = if trade.pnl_usd >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let fill_style = if trade.fill_type == "maker" {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let mut parts = vec![
        Span::styled(format!("#{:<3} ", trade.index), app.theme.muted),
        Span::styled(
            format!("{} {}", direction_icon, direction_initial(trade)),
            direction_style,
        ),
        Span::styled(format!(" {:+.2} ", trade.pnl_usd), pnl_style),
    ];
    parts.extend(trade_bar(trade, age, max_age));
    parts.push(Span::styled(
        format!(" {:+.2}%", trade.margin_pnl_pct),
        app.theme.muted,
    ));
    parts.push(Span::raw("  "));
    parts.push(Span::styled(format!("[{}]", trade.fill_type), fill_style));
    parts.push(Span::styled(
        format!(" {}", exit_label(trade)),
        app.theme.muted,
    ));
    Line::from(parts)
}

fn trade_bar(trade: &HypervelocityTrade, age: usize, max_age: usize) -> Vec<Span<'static>> {
    let width = 40usize;
    let filled = ((trade.margin_pnl_pct.abs() / 12.0).min(1.0) * width as f64) as usize;
    (0..width)
        .map(|index| {
            let character = if index < filled.min(width) {
                if trade.pnl_usd >= 0.0 { '█' } else { '░' }
            } else {
                '·'
            };
            let zone = index as f64 / width as f64 * 12.0;
            let base_color = if trade.pnl_usd >= 0.0 {
                animation::gradient_color(zone, 0)
            } else {
                ratatui::style::Color::Rgb(255, 60, 60)
            };
            let color = animation::aged_color(base_color, age, max_age);
            Span::styled(character.to_string(), Style::default().fg(color))
        })
        .collect()
}

fn trade_direction(app: &App, trade: &HypervelocityTrade) -> (&'static str, Style) {
    if trade.direction == "LONG" {
        ("▲", app.theme.bull)
    } else {
        ("▼", app.theme.bear)
    }
}

fn direction_initial(trade: &HypervelocityTrade) -> &'static str {
    if trade.direction == "LONG" { "L" } else { "S" }
}

fn exit_label(trade: &HypervelocityTrade) -> &str {
    match trade.exit_reason.as_str() {
        "tp1" | "tp2" | "tp1+tp2" => trade.exit_reason.as_str(),
        "SL" => "SL",
        "OPEN" => "OPEN",
        "TREND_UP" | "TREND_DOWN" | "BREAKOUT" | "TRANSITION" | "RANGE" => "regime",
        value
            if value.contains("MOMENTUM")
                || value.contains("COILING")
                || value.contains("CARRY")
                || value.contains("CHOP") =>
        {
            "regime"
        }
        _ => &trade.exit_reason,
    }
}

fn render_equity_sparkline(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Length(3)])
        .split(area);
    render_equity_curve(f, app, chunks[0]);
    render_performance_summary(f, app, chunks[1]);
}

fn render_equity_curve(f: &mut Frame, app: &App, area: Rect) {
    let equity_data = app.sparkline_equity_data();
    let sparkline = Sparkline::default()
        .block(
            Block::default()
                .title(" EQUITY CURVE (60-bar rolling) ")
                .title_style(app.theme.title)
                .borders(Borders::ALL)
                .border_style(app.theme.border),
        )
        .data(&equity_data)
        .style(app.theme.bull);
    f.render_widget(sparkline, area);
}

fn performance_summary_lines(app: &App) -> Vec<Line<'static>> {
    let leverage = effective_backend_leverage(app)
        .map(|value| format!("{value:.1}x"))
        .unwrap_or_else(|| "n/a".to_string());
    let target = backend_number(&app.backend.strategy_params, "target_margin_pct")
        .map(|value| format!("{value:.1}%"))
        .unwrap_or_else(|| "n/a".to_string());
    let return_pct = if app.paper_stats.initial_capital.abs() > f64::EPSILON {
        (app.paper_stats.current_equity - app.paper_stats.initial_capital)
            / app.paper_stats.initial_capital
            * 100.0
    } else {
        0.0
    };
    vec![
        Line::from(vec![Span::styled(
            format!(
                "EQUITY ${:.2}  │  {:+.1}%  │  TARGET {}  │  {}",
                app.paper_stats.current_equity, return_pct, target, leverage,
            ),
            app.theme.muted,
        )]),
        Line::from(vec![Span::styled(
            format!(
                "{} TRADES  │  {:.1}% WIN  │  {}x PF",
                app.paper_stats.total_trades,
                app.paper_stats.win_rate_pct,
                if app.paper_stats.losses == 0 {
                    "∞".to_string()
                } else {
                    format!("{:.2}", app.paper_stats.profit_factor)
                }
            ),
            app.theme.muted,
        )]),
    ]
}

fn render_performance_summary(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(" PERFORMANCE SUMMARY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(
        Paragraph::new(performance_summary_lines(app)).block(block),
        area,
    );
}
