//! Strategy policy, portfolio, and risk dashboard composition.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use super::{logs, policy_panels, regime_widgets};
use crate::{app::App, hypervelocity};

pub(super) fn render(f: &mut Frame, app: &App, area: Rect) {
    if app.backend.is_apex_mm() {
        crate::apex_mm_view::render_dashboard(f, app, area);
        return;
    }
    if app.backend.is_pine_stack() {
        crate::pine_stack_view::render_dashboard(f, app, area);
        return;
    }
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6),
            Constraint::Length(4),
            Constraint::Length(14),
            Constraint::Length(6),
            Constraint::Min(6),
        ])
        .split(area);
    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(42), Constraint::Percentage(58)])
        .split(chunks[0]);
    hypervelocity::render_command_bar(f, app, top[0]);
    render_dynamic_leverage_panel(f, app, top[1]);
    policy_panels::render_registered_strategy_matrix(f, app, chunks[1]);
    hypervelocity::render_position_and_book(f, app, chunks[2]);
    render_performance(f, app, chunks[3]);
    render_journal_section(f, app, chunks[4]);
}

fn render_performance(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(34),
            Constraint::Percentage(33),
            Constraint::Percentage(33),
        ])
        .split(area);
    render_portfolio_telemetry(f, app, chunks[0]);
    hypervelocity::render_all_time_stats(f, app, chunks[1]);
    hypervelocity::render_run_stats(f, app, chunks[2]);
}

fn render_portfolio_telemetry(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .title(portfolio_telemetry_title(app))
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(portfolio_lines(app)).block(block), area);
}

fn portfolio_lines(app: &App) -> Vec<Line<'static>> {
    let stats = &app.paper_stats;
    let net_pnl = stats.current_equity - stats.initial_capital;
    let pnl_style = if net_pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let equity_pct = net_pnl / stats.initial_capital * 100.0;
    vec![
        Line::from(vec![
            Span::raw("INITIAL CAP: "),
            Span::styled(format!("${:.2}", stats.initial_capital), app.theme.title),
            Span::raw("  EQUITY: "),
            Span::styled(
                format!("${:.2} ({equity_pct:+.2}%)", stats.current_equity),
                pnl_style,
            ),
        ]),
        Line::from(vec![
            Span::raw("NET PNL:     "),
            Span::styled(format!("{:+.2} USD", normalized_zero(net_pnl)), pnl_style),
            Span::raw("  MARGIN: "),
            Span::styled(portfolio_margin_display(app), app.theme.gold),
        ]),
        Line::from(vec![
            Span::raw("EXECUTION:   "),
            Span::styled(execution_display(app), app.theme.cyan),
        ]),
        win_rate_line(app),
    ]
}

fn win_rate_line(app: &App) -> Line<'static> {
    let stats = &app.paper_stats;
    let style = if stats.win_rate_pct >= 50.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    Line::from(vec![
        Span::raw("TOTAL TRADES: "),
        Span::styled(stats.total_trades.to_string(), app.theme.gold),
        Span::raw("  WIN RATE: "),
        Span::styled(
            format!(
                "{:.1}% ({}W/{}L)",
                stats.win_rate_pct, stats.wins, stats.losses
            ),
            style,
        ),
    ])
}

fn portfolio_telemetry_title(app: &App) -> &'static str {
    match (
        app.backend.execution_mode.as_deref(),
        app.backend.live_enabled,
        app.backend.live_armed,
        app.backend.portfolio_purpose.as_deref(),
    ) {
        (Some("live"), Some(true), Some(true), _) => " LIVE ACCOUNT PORTFOLIO ",
        (Some("live"), _, _, _) => " LIVE ACCOUNT DISARMED ",
        (Some("shadow" | "paper"), _, _, _) => " SHADOW PORTFOLIO ",
        _ => " BACKEND PORTFOLIO TELEMETRY ",
    }
}

fn portfolio_margin_display(app: &App) -> String {
    let Some(fraction) = backend_f64(&app.backend.risk, "margin_fraction") else {
        return "not reported".to_string();
    };
    let allocated = if app.active_position.is_active() && app.active_position.leverage > 0.0 {
        app.active_position.entry_price * app.active_position.size_btc
            / app.active_position.leverage
    } else {
        app.paper_stats.current_equity * fraction
    };
    format!("${allocated:.2} ({:.0}% Alloc)", fraction * 100.0)
}

fn execution_display(app: &App) -> String {
    let mode = app
        .backend
        .execution_mode
        .as_deref()
        .unwrap_or("not reported")
        .to_uppercase();
    let time_in_force = app
        .backend
        .execution_policy
        .get("time_in_force")
        .and_then(serde_json::Value::as_str);
    let maker_fee = backend_f64(&app.backend.costs, "maker_fee_rate");
    match (time_in_force, maker_fee) {
        (Some("post_only"), Some(fee)) => {
            format!("{mode} | POST-ONLY MAKER | {:.2}bps/side", fee * 10_000.0)
        }
        _ => format!("{mode} | backend execution costs not reported"),
    }
}

fn render_journal_section(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(4)])
        .split(area);
    regime_widgets::render_distribution_bar(f, app, chunks[0]);
    logs::render_paper_journal_log(f, app, chunks[1]);
}

fn render_dynamic_leverage_panel(f: &mut Frame, app: &App, area: Rect) {
    if policy_panels::render_specialized_policy(f, app, area) {
        return;
    }
    let block = Block::default()
        .title(" BACKEND ENTRY POLICY & ACCOUNT TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(dynamic_policy_lines(app)).block(block), area);
}

fn dynamic_policy_lines(app: &App) -> Vec<Line<'static>> {
    let snap = app.current_snapshot();
    let leverage = ratio_bar(snap.dynamic_leverage, snap.max_leverage, 12);
    let long = fraction_bar(snap.long_weight, 10);
    let short = fraction_bar(snap.short_weight, 10);
    let (eligible, eligible_style) = eligible_side(app);
    vec![
        Line::from(vec![
            Span::raw("Eligible Leverage: "),
            Span::styled(
                format!(
                    "{leverage} {:.2}x / {:.1}x",
                    snap.dynamic_leverage, snap.max_leverage
                ),
                app.theme.gold,
            ),
            Span::raw(" │ Eligible Side: "),
            Span::styled(eligible, eligible_style),
        ]),
        Line::from(vec![
            Span::raw("Long Eligible: "),
            Span::styled(
                format!("{long} {:.0}%", snap.long_weight.clamp(0.0, 1.0) * 100.0),
                app.theme.bull,
            ),
            Span::raw(" │ Short Eligible: "),
            Span::styled(
                format!("{short} {:.0}%", snap.short_weight.clamp(0.0, 1.0) * 100.0),
                app.theme.bear,
            ),
        ]),
        flow_line(app),
        account_line(app),
    ]
}

fn ratio_bar(value: f64, maximum: f64, width: usize) -> String {
    let fraction = if maximum > 0.0 {
        (value / maximum).clamp(0.0, 1.0)
    } else {
        0.0
    };
    fraction_bar_width(fraction, width)
}

fn fraction_bar(value: f64, width: usize) -> String {
    fraction_bar_width(value.clamp(0.0, 1.0), width)
}

fn fraction_bar_width(fraction: f64, width: usize) -> String {
    let filled = (fraction * width as f64) as usize;
    format!("[{}{}]", "█".repeat(filled), "░".repeat(width - filled))
}

fn eligible_side(app: &App) -> (String, ratatui::style::Style) {
    let snap = app.current_snapshot();
    let net = snap.long_weight - snap.short_weight;
    if net > 0.0 {
        ("LONG".into(), app.theme.bull)
    } else if net < 0.0 {
        ("SHORT".into(), app.theme.bear)
    } else {
        ("NONE".into(), app.theme.gold)
    }
}

fn flow_line(app: &App) -> Line<'static> {
    let snap = app.current_snapshot();
    Line::from(if snap.microstructure_source == "not_available" {
        format!("OPI Flow: not reported │ RSI (14): {:.1}", snap.rsi)
    } else {
        format!("OPI Flow: {:+.2} │ RSI (14): {:.1}", snap.opi, snap.rsi)
    })
}

fn account_line(app: &App) -> Line<'static> {
    let stats = &app.paper_stats;
    let pnl_style = if stats.realized_pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let taker_style = if app.current_snapshot().taker_allowed {
        app.theme.bull
    } else {
        app.theme.gold
    };
    Line::from(vec![
        Span::raw("Account: Equity "),
        Span::styled(format!("${:.2}", stats.current_equity), app.theme.title),
        Span::raw(" │ PnL "),
        Span::styled(format!("{:+.2}", stats.realized_pnl), pnl_style),
        Span::raw(" │ Execution: "),
        Span::styled(
            if app.current_snapshot().taker_allowed {
                "TAKERS PERMITTED"
            } else {
                "MAKER ONLY"
            },
            taker_style,
        ),
    ])
}

pub(super) fn backend_f64(value: &serde_json::Value, key: &str) -> Option<f64> {
    value.get(key).and_then(serde_json::Value::as_f64)
}

pub(super) fn normalized_zero(value: f64) -> f64 {
    if value.abs() < 0.005 { 0.0 } else { value }
}
